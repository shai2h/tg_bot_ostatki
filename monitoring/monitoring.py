import asyncio
import logging
import aiohttp
import subprocess
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from sqlalchemy import select, insert, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db.database import async_session_maker
from app.config import settings
from .models import MonitoringStatus, MonitoringLog
from .telegram_notifier import TelegramNotifier

logger = logging.getLogger(__name__)

class SystemMonitor:
    def __init__(self):
        self.telegram = TelegramNotifier()
        self.is_running = False
        
    async def start_monitoring(self):
        """Основной цикл мониторинга"""
        self.is_running = True
        logger.info("Запуск системы мониторинга")
        
        # Инициализация статусов в БД
        await self._init_monitoring_status()
        
        # Запуск задач мониторинга
        tasks = [
            asyncio.create_task(self._monitor_api_1c()),
            asyncio.create_task(self._monitor_telegram_bot()),
        ]
        
        try:
            await asyncio.gather(*tasks)
        except Exception as e:
            logger.error(f"Критическая ошибка мониторинга: {e}")
            await self._log_event("system", "critical_error", str(e), "critical")
        finally:
            self.is_running = False
    
    async def _init_monitoring_status(self):
        """Инициализация записей мониторинга в БД"""
        components = ['api_1c', 'telegram_bot']
        
        async with async_session_maker() as session:
            for component in components:
                stmt = pg_insert(MonitoringStatus).values(
                    component=component,
                    status='unknown',
                    last_check=datetime.utcnow(),
                    error_count=0,
                    notification_sent=False
                )
                stmt = stmt.on_conflict_do_nothing(index_elements=['component'])
                await session.execute(stmt)
            await session.commit()
    
    async def _monitor_api_1c(self):
        """Мониторинг API запросов от 1С"""
        while self.is_running:
            try:
                await self._check_api_1c_activity()
                await asyncio.sleep(settings.API_CHECK_INTERVAL)
            except Exception as e:
                logger.error(f"Ошибка в мониторинге API 1С: {e}")
                await asyncio.sleep(30)  # Короткая пауза при ошибке
    
    async def _monitor_telegram_bot(self):
        """Мониторинг работы Telegram бота"""
        while self.is_running:
            try:
                await self._check_telegram_bot_health()
                await asyncio.sleep(settings.BOT_CHECK_INTERVAL)
            except Exception as e:
                logger.error(f"Ошибка в мониторинге Telegram бота: {e}")
                await asyncio.sleep(30)
    
    async def _check_api_1c_activity(self):
        """Проверка активности API 1С по времени последнего обновления"""
        async with async_session_maker() as session:
            # Проверяем время последнего обновления в таблице ostatki_meta
            from app.warehouse_stock.models import OstatkiMeta
            
            result = await session.execute(
                select(OstatkiMeta.last_updated).where(OstatkiMeta.id == 1)
            )
            last_update = result.scalar_one_or_none()
            
            current_status = await self._get_component_status('api_1c')
            now = datetime.utcnow()
            
            if last_update is None:
                # Никогда не было обновлений
                await self._update_status('api_1c', 'error', 
                                        'API 1С: данные никогда не поступали')
                return
            
            # Проверяем, давно ли было последнее обновление
            time_diff = now - last_update
            threshold = timedelta(seconds=settings.API_TIMEOUT_THRESHOLD)
            
            if time_diff > threshold:
                # Проблема: нет запросов
                if current_status['status'] != 'error':
                    message = f"🔴 Проблема: запросы с 1С не приходят уже {int(time_diff.total_seconds()/60)} минут"
                    await self._update_status('api_1c', 'error', message)
                    await self.telegram.send_alert(message)
                    await self._log_event('api_1c', 'status_change', message, 'error')
            else:
                # Все хорошо
                if current_status['status'] == 'error':
                    message = "✅ ОК: Запросы с 1С вернулись к работе"
                    await self._update_status('api_1c', 'ok', message)
                    await self.telegram.send_recovery(message)
                    await self._log_event('api_1c', 'recovery', message, 'info')
                elif current_status['status'] != 'ok':
                    await self._update_status('api_1c', 'ok', 'API 1С работает нормально')
    
    async def _check_telegram_bot_health(self):
        """Проверка работы Telegram бота через HTTP запрос"""
        try:
            # Проверяем доступность основного API
            api_url = f"http://{settings.API_HOST}:{settings.API_PORT}/docs"
            
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
                async with session.get(api_url) as response:
                    if response.status == 200:
                        # API отвечает
                        current_status = await self._get_component_status('telegram_bot')
                        if current_status['status'] == 'error':
                            message = "✅ ОК: Telegram бот вернулся к работе"
                            await self._update_status('telegram_bot', 'ok', message)
                            await self.telegram.send_recovery(message)
                            await self._log_event('telegram_bot', 'recovery', message, 'info')
                        elif current_status['status'] != 'ok':
                            await self._update_status('telegram_bot', 'ok', 'Telegram бот работает')
                    else:
                        raise aiohttp.ClientError(f"HTTP {response.status}")
                        
        except Exception as e:
            # Бот не отвечает
            current_status = await self._get_component_status('telegram_bot')
            if current_status['status'] != 'error':
                message = f"🔴 Проблема: Telegram бот не отвечает. Пытаюсь перезагрузить..."
                await self._update_status('telegram_bot', 'error', str(e))
                await self.telegram.send_alert(message)
                await self._log_event('telegram_bot', 'status_change', message, 'error')
                
                # Пытаемся перезапустить
                restart_result = await self._restart_telegram_bot()
                restart_message = f"Результат перезапуска: {restart_result}"
                await self.telegram.send_alert(restart_message)
                await self._log_event('telegram_bot', 'restart_attempt', restart_message, 'warning')
    
    async def _restart_telegram_bot(self) -> str:
        """Перезапуск Telegram бота через systemctl"""
        try:
            # Перезапуск службы
            result = subprocess.run(
                ['sudo', 'systemctl', 'restart', 'tg-bot.service'],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                # Ждем немного и проверяем статус
                await asyncio.sleep(10)
                
                status_result = subprocess.run(
                    ['sudo', 'systemctl', 'is-active', 'tg-bot.service'],
                    capture_output=True,
                    text=True
                )
                
                if status_result.stdout.strip() == 'active':
                    return "✅ Служба успешно перезапущена"
                else:
                    return f"⚠️ Служба перезапущена, но статус: {status_result.stdout.strip()}"
            else:
                return f"❌ Ошибка перезапуска: {result.stderr}"
                
        except subprocess.TimeoutExpired:
            return "⏰ Тайм-аут при перезапуске службы"
        except Exception as e:
            return f"❌ Критическая ошибка при перезапуске: {str(e)}"
    
    async def _get_component_status(self, component: str) -> Dict[str, Any]:
        """Получение текущего статуса компонента"""
        async with async_session_maker() as session:
            result = await session.execute(
                select(MonitoringStatus).where(MonitoringStatus.component == component)
            )
            status_obj = result.scalar_one_or_none()
            
            if status_obj:
                return {
                    'status': status_obj.status,
                    'last_check': status_obj.last_check,
                    'last_success': status_obj.last_success,
                    'error_count': status_obj.error_count,
                    'notification_sent': status_obj.notification_sent
                }
            return {'status': 'unknown', 'error_count': 0, 'notification_sent': False}
    
    async def _update_status(self, component: str, status: str, message: str):
        """Обновление статуса компонента"""
        async with async_session_maker() as session:
            now = datetime.utcnow()
            
            update_data = {
                'status': status,
                'last_check': now,
                'error_message': message,
                'updated_at': now
            }
            
            if status == 'ok':
                update_data['last_success'] = now
                update_data['error_count'] = 0
                update_data['notification_sent'] = False
            else:
                # Увеличиваем счетчик ошибок
                current = await self._get_component_status(component)
                update_data['error_count'] = current['error_count'] + 1
            
            stmt = update(MonitoringStatus).where(
                MonitoringStatus.component == component
            ).values(**update_data)
            
            await session.execute(stmt)
            await session.commit()
    
    async def _log_event(self, component: str, event_type: str, message: str, severity: str):
        """Логирование событий мониторинга"""
        async with async_session_maker() as session:
            stmt = insert(MonitoringLog).values(
                component=component,
                event_type=event_type,
                message=message,
                severity=severity,
                created_at=datetime.utcnow()
            )
            await session.execute(stmt)
            await session.commit()
        
        # Также пишем в обычный лог
        log_level = getattr(logging, severity.upper(), logging.INFO)
        logger.log(log_level, f"[{component}] {event_type}: {message}")
    
    async def stop_monitoring(self):
        """Остановка мониторинга"""
        self.is_running = False
        logger.info("Остановка системы мониторинга")
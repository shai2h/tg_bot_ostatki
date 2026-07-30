# Настройки, подключение, логика

# Функция скрытия остатков.
def format_stock_quantity(ostatok: str) -> str:
    try:
        count = int(str(ostatok).strip())
        if count == 1:
            return "в наличии"
        elif 1 < count <= 4:
            return "несколько"
        elif count > 4:
            return "много"
    except Exception:
        return str(ostatok) or "нет"

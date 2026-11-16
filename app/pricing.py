class PricingError(ValueError):
    pass


def compute_price(base_price, percent_off):
    for value in (base_price, percent_off):
        if isinstance(value, bool) or not isinstance(value, int):
            raise PricingError("price inputs must be whole numbers")
    if base_price < 0 or not 0 <= percent_off <= 100:
        raise PricingError("price inputs out of range")
    return (base_price * (100 - percent_off) + 50) // 100


def get_price(conn, route_code, pass_type, concession):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT r.id AS route_id, r.daily_capacity, r.active, f.price_pkr, f.duration_days "
            "FROM routes r JOIN fares f ON f.route_id = r.id "
            "WHERE r.code = %s AND f.pass_type = %s",
            (route_code, pass_type),
        )
        fare = cur.fetchone()
        cur.execute("SELECT percent_off FROM concessions WHERE code = %s", (concession,))
        discount = cur.fetchone()
    if not fare or not fare["active"]:
        raise PricingError("unknown route or pass type")
    if not discount:
        raise PricingError("unknown concession")
    return {
        "route_id": fare["route_id"],
        "daily_capacity": fare["daily_capacity"],
        "duration_days": fare["duration_days"],
        "base_price_pkr": fare["price_pkr"],
        "percent_off": discount["percent_off"],
        "price_pkr": compute_price(fare["price_pkr"], discount["percent_off"]),
    }
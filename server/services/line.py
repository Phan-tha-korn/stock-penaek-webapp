import httpx
import logging
from server.config.settings import settings

logger = logging.getLogger(__name__)

async def send_line_notify(role: str, message: str) -> bool:
    token = getattr(settings, f"line_token_{role.lower()}", "")
    if not token:
        logger.warning(f"No LINE Notify token configured for role: {role}")
        return False
        
    try:
        async with httpx.AsyncClient() as client:
            res = await client.post(
                "https://notify-api.line.me/api/notify",
                headers={"Authorization": f"Bearer {token}"},
                data={"message": message}
            )
            res.raise_for_status()
            return True
    except Exception as e:
        logger.error(f"Failed to send LINE Notify to {role}: {e}")
        return False

async def notify_low_stock(product) -> None:
    restock = float(product.max_stock) - float(product.stock_qty)
    msg = (
        f"\n[STOCK ALERT] {product.name.get('th', product.sku)}\n"
        f"สถานะ: {product.status.value}\n"
        f"คงเหลือ: {product.stock_qty} {product.unit}\n"
        f"ควรมี: {product.max_stock} {product.unit}\n"
        f"ต้องเติม: {restock} {product.unit}"
    )
    await send_line_notify("stock", msg)

"""
Email yuborish funksiyalari.

send_email()                 - umumiy funksiya
send_order_confirmation()    - buyurtma tasdiqlash xati
send_order_status_update()   - buyurtma holati o'zgargani haqida xat
send_password_reset_email()  - parolni tiklash xati
"""
import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.utils.html import escape

logger = logging.getLogger(__name__)


def send_email(subject, message, recipient_list, html_message=None):
    """Email yuboradi. Muvaffaqiyatli bo'lsa True, aks holda False qaytaradi."""
    if isinstance(recipient_list, str):
        recipient_list = [recipient_list]
    recipient_list = [r for r in recipient_list if r]
    if not recipient_list:
        return False

    try:
        email = EmailMultiAlternatives(
            subject=subject,
            body=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=recipient_list,
        )
        if html_message:
            email.attach_alternative(html_message, "text/html")
        email.send(fail_silently=False)
        return True
    except Exception:
        logger.exception("Email yuborishda xatolik: %s", recipient_list)
        return False


def send_order_confirmation(order):
    items = list(order.items.all())
    lines = [f"- {i.product_name} x {i.quantity} = {i.subtotal} so'm" for i in items]
    rows = "".join(
        f"<tr><td>{escape(i.product_name)}</td><td>{i.quantity}</td>"
        f"<td>{i.subtotal} so'm</td></tr>"
        for i in items
    )
    subject = f"Buyurtmangiz qabul qilindi (#{order.pk})"
    message = (
        f"Assalomu alaykum, {order.customer_name}!\n\n"
        f"Buyurtmangiz #{order.pk} qabul qilindi.\n\n"
        + "\n".join(lines)
        + f"\n\nJami: {order.total_price} so'm\nManzil: {order.address}\n\n"
        "Xaridingiz uchun rahmat!"
    )
    html = f"""
    <h2>Assalomu alaykum, {escape(order.customer_name)}!</h2>
    <p>Buyurtmangiz <b>#{order.pk}</b> qabul qilindi.</p>
    <table border="1" cellpadding="6" cellspacing="0">
      <tr><th>Mahsulot</th><th>Soni</th><th>Narxi</th></tr>{rows}
    </table>
    <p><b>Jami: {order.total_price} so'm</b></p>
    <p>Manzil: {escape(order.address)}</p>
    <p>Xaridingiz uchun rahmat!</p>
    """
    return send_email(subject, message, [order.user.email], html)


def send_order_status_update(order):
    subject = f"Buyurtma #{order.pk} holati: {order.get_status_display()}"
    message = (
        f"Assalomu alaykum, {order.customer_name}!\n\n"
        f"Buyurtmangiz #{order.pk} holati o'zgardi: {order.get_status_display()}."
    )
    return send_email(subject, message, [order.user.email])


def send_password_reset_email(user, uid, token):
    link = f"{settings.FRONTEND_URL}/reset-password?uid={uid}&token={token}"
    subject = "Parolni tiklash"
    message = (
        f"Assalomu alaykum, {user.username}!\n\n"
        f"Parolni tiklash uchun havola:\n{link}\n\n"
        f"uid: {uid}\ntoken: {token}\n\n"
        "Agar bu so'rovni siz yubormagan bo'lsangiz, xatni e'tiborsiz qoldiring."
    )
    return send_email(subject, message, [user.email])

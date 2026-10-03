"""
Regex asosidagi validatorlar: username, email, telefon raqam, parol.
Signup va Login'da ishlatiladi.
"""
import re

from django.core.exceptions import ValidationError

# Username: 3-20 belgi, harf bilan boshlanadi, faqat lotin harflari, raqam va _
USERNAME_REGEX = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]{2,19}$")

# Email: nom@domen.tld
EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9-]+(\.[a-zA-Z0-9-]+)*\.[a-zA-Z]{2,}$")

# Telefon (O'zbekiston): +998 va 9 ta raqam, masalan +998901234567
PHONE_REGEX = re.compile(r"^\+998\d{9}$")

# Parol: kamida 8 belgi, kamida 1 ta harf va 1 ta raqam
PASSWORD_REGEX = re.compile(r"^(?=.*[A-Za-z])(?=.*\d).{8,}$")


def validate_username(value):
    if not USERNAME_REGEX.match(value):
        raise ValidationError(
            "Username 3-20 belgidan iborat bo'lishi, harf bilan boshlanishi va "
            "faqat lotin harflari, raqam va _ dan iborat bo'lishi kerak."
        )
    return value


def validate_email_format(value):
    if not EMAIL_REGEX.match(value):
        raise ValidationError("Email noto'g'ri formatda. Masalan: ali@mail.com")
    return value.lower()


def normalize_phone(value):
    """Bo'sh joy, tire va qavslarni olib tashlaydi: '+998 (90) 123-45-67' -> '+998901234567'"""
    return re.sub(r"[\s\-()]", "", value)


def validate_phone(value):
    value = normalize_phone(value)
    if not PHONE_REGEX.match(value):
        raise ValidationError(
            "Telefon raqam noto'g'ri. Format: +998901234567"
        )
    return value


def validate_password_strength(value):
    if not PASSWORD_REGEX.match(value):
        raise ValidationError(
            "Parol kamida 8 belgidan iborat bo'lib, kamida 1 ta harf va 1 ta raqam bo'lishi kerak."
        )
    return value

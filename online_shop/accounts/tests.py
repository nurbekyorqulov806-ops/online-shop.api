from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, override_settings
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework.test import APITestCase

from . import validators as v


class RegexTests(SimpleTestCase):
    def test_username(self):
        for ok in ["ali", "Ali_123", "a_b"]:
            self.assertTrue(v.USERNAME_REGEX.match(ok), ok)
        for bad in ["a", "1ali", "ali baliyev", "ali!", "a" * 21]:
            self.assertFalse(v.USERNAME_REGEX.match(bad), bad)

    def test_email(self):
        for ok in ["ali@mail.com", "a.b+c@sub.domain.uz"]:
            self.assertTrue(v.EMAIL_REGEX.match(ok), ok)
        for bad in ["ali@", "@mail.com", "ali@mail", "ali mail@x.com"]:
            self.assertFalse(v.EMAIL_REGEX.match(bad), bad)

    def test_phone(self):
        self.assertEqual(v.validate_phone("+998 (90) 123-45-67"), "+998901234567")
        for bad in ["901234567", "+99890123456", "+9989012345678", "+998abc"]:
            with self.assertRaises(ValidationError):
                v.validate_phone(bad)

    def test_password(self):
        self.assertTrue(v.PASSWORD_REGEX.match("abc12345"))
        for bad in ["abcdefgh", "12345678", "ab12"]:
            self.assertFalse(v.PASSWORD_REGEX.match(bad), bad)


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class AuthTests(APITestCase):
    data = {
        "username": "ali",
        "email": "ali@mail.com",
        "phone": "+998901234567",
        "password": "parol1234",
        "password2": "parol1234",
    }

    def signup(self, **extra):
        return self.client.post("/api/auth/signup/", {**self.data, **extra}, format="json")

    def authenticate(self, **extra):
        token = self.signup(**extra).data["token"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token}")

    def login(self, login, password):
        return self.client.post(
            "/api/auth/login/", {"login": login, "password": password}, format="json"
        )

    # ---- signup / login / logout ----
    def test_signup_ok_and_welcome_email(self):
        r = self.signup()
        self.assertEqual(r.status_code, 201)
        self.assertIn("token", r.data)
        self.assertEqual(len(mail.outbox), 1)

    def test_signup_invalid_fields(self):
        self.assertEqual(self.signup(username="1ali").status_code, 400)
        self.assertEqual(self.signup(email="bad@").status_code, 400)
        self.assertEqual(self.signup(phone="123").status_code, 400)
        self.assertEqual(self.signup(password="short", password2="short").status_code, 400)
        self.assertEqual(self.signup(password2="boshqa1234").status_code, 400)

    def test_signup_duplicates(self):
        self.signup()
        self.assertEqual(self.signup().status_code, 400)

    def test_login_by_username_email_phone(self):
        self.signup()
        for login in ["ali", "ali@mail.com", "+998901234567"]:
            r = self.login(login, "parol1234")
            self.assertEqual(r.status_code, 200, login)
            self.assertIn("token", r.data)

    def test_login_wrong_password_and_format(self):
        self.signup()
        self.assertEqual(self.login("ali", "xato").status_code, 400)
        self.assertEqual(self.login("!!", "x").status_code, 400)

    def test_login_works_with_stale_token_header(self):
        self.signup()
        self.client.credentials(HTTP_AUTHORIZATION="Token eskitoken")
        self.assertEqual(self.login("ali", "parol1234").status_code, 200)

    def test_logout(self):
        self.authenticate()
        self.assertEqual(self.client.post("/api/auth/logout/").status_code, 200)

    # ---- profil ----
    def test_me_get_and_update(self):
        self.authenticate()
        r = self.client.get("/api/auth/me/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["username"], "ali")
        self.assertEqual(r.data["phone"], "+998901234567")

        r = self.client.patch(
            "/api/auth/me/",
            {"first_name": "Ali", "phone": "+998 91 111 22 33"},
            format="json",
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["first_name"], "Ali")
        self.assertEqual(r.data["phone"], "+998911112233")

    def test_me_requires_auth(self):
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 401)

    def test_me_duplicate_phone(self):
        self.signup(username="vali", email="vali@mail.com", phone="+998933334455")
        self.authenticate()
        r = self.client.patch("/api/auth/me/", {"phone": "+998933334455"}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_delete_account(self):
        self.authenticate()
        r = self.client.delete("/api/auth/me/", {"password": "xato"}, format="json")
        self.assertEqual(r.status_code, 400)
        r = self.client.delete("/api/auth/me/", {"password": "parol1234"}, format="json")
        self.assertEqual(r.status_code, 204)
        self.assertFalse(User.objects.filter(username="ali").exists())

    # ---- parol ----
    def test_change_password(self):
        self.authenticate()
        bad = {"old_password": "xato", "new_password": "yangi5678", "new_password2": "yangi5678"}
        self.assertEqual(
            self.client.post("/api/auth/change-password/", bad, format="json").status_code, 400
        )
        ok = {"old_password": "parol1234", "new_password": "yangi5678", "new_password2": "yangi5678"}
        r = self.client.post("/api/auth/change-password/", ok, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertIn("token", r.data)

        self.client.credentials()
        self.assertEqual(self.login("ali", "yangi5678").status_code, 200)
        self.assertEqual(self.login("ali", "parol1234").status_code, 400)

    def test_password_reset_flow(self):
        user = User.objects.create_user("vali", "vali@mail.com", "eski12345")
        r = self.client.post("/api/auth/password-reset/", {"email": "vali@mail.com"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)

        # Mavjud bo'lmagan email uchun ham javob bir xil, xat yuborilmaydi
        r = self.client.post("/api/auth/password-reset/", {"email": "yoq@mail.com"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)

        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        payload = {"uid": uid, "token": token, "new_password": "yangi5678", "new_password2": "yangi5678"}

        bad = {**payload, "token": "noto'g'ri"}
        self.assertEqual(
            self.client.post("/api/auth/password-reset/confirm/", bad, format="json").status_code, 400
        )
        r = self.client.post("/api/auth/password-reset/confirm/", payload, format="json")
        self.assertEqual(r.status_code, 200)
        user.refresh_from_db()
        self.assertTrue(user.check_password("yangi5678"))

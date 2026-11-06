from django.test import TestCase, RequestFactory
from django.contrib.auth.models import User
from .models import Mess, UserMessAccess, Member, set_tenant_context, reset_tenant_context

class MessHierarchyTests(TestCase):
    def setUp(self):
        self.mess_a = Mess.objects.create(name="Mess A", code="A")
        self.mess_b = Mess.objects.create(name="Mess B", code="B")
        self.user = User.objects.create_user(username="accountant", password="test-pass")
        UserMessAccess.objects.create(user=self.user, mess=self.mess_a, role=UserMessAccess.ACCOUNTANT)

    def test_accountant_scope_hides_other_mess(self):
        Member.all_objects.create(mess=self.mess_a, member_no="1", name="A member")
        Member.all_objects.create(mess=self.mess_b, member_no="1", name="B member")
        tokens = set_tenant_context([self.mess_a.pk], self.mess_a.pk)
        try:
            self.assertEqual(Member.objects.count(), 1)
            self.assertEqual(Member.objects.first().name, "A member")
        finally:
            reset_tenant_context(tokens)

    def test_same_member_number_allowed_in_different_messes(self):
        Member.all_objects.create(mess=self.mess_a, member_no="1", name="A member")
        Member.all_objects.create(mess=self.mess_b, member_no="1", name="B member")
        self.assertEqual(Member.all_objects.count(), 2)

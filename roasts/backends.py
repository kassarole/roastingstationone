import logging

from mozilla_django_oidc.auth import OIDCAuthenticationBackend
from django.contrib.auth.models import Group, Permission

logger = logging.getLogger(__name__)


class CustomOIDCBackend(OIDCAuthenticationBackend):
    # Authentik group name -> Django group name mapping.
    GROUP_MAP = {
        "Coffee Roaster": "Coffee Roaster",
        "roast-viewers": "Viewers",
    }

    # Groups that should exist regardless of who has logged in yet, so admins
    # can attach permissions to them in the Django admin in advance.
    DEFAULT_GROUPS = ("Coffee Roaster", "Viewers")

    # Django group whose members are granted is_staff.
    STAFF_GROUP = "Coffee Roaster"

    # Permissions every authenticated user gets directly (not via a group).
    BASE_ROAST_PERMS = [
        "add_roast",
        "change_roast",
        "delete_roast",
        "view_roast",
        "add_roastcomment",
        "change_roastcomment",
        "delete_roastcomment",
        "view_roastcomment",   
    ]

    # --- user creation / update ------------------------------------------

    def create_user(self, claims):
        user = super().create_user(claims)
        self._apply_identity(user, claims)
        self.update_groups(user, claims)
        return user

    def update_user(self, user, claims):
        user = super().update_user(user, claims)
        self._apply_identity(user, claims)
        self.update_groups(user, claims)
        return user

    def _apply_identity(self, user, claims):
        """Set username/email from Authentik claims on every login."""
        desired_username = self.get_username(claims)
        desired_email = self.get_email(claims)

        changed = []
        if desired_username and user.username != desired_username:
            if not self.UserModel.objects.exclude(pk=user.pk).filter(
                username=desired_username
            ).exists():
                user.username = desired_username
                changed.append("username")
            else:
                logger.warning(
                    "OIDC: desired username %r already taken; keeping %r",
                    desired_username, user.username,
                )

        if desired_email and user.email != desired_email:
            user.email = desired_email
            changed.append("email")

        if changed:
            user.save(update_fields=changed)

    # --- claim extraction -------------------------------------------------

    def get_username(self, claims):
        return (
            claims.get("preferred_username")
            or claims.get("username")
            or (claims.get("email", "").split("@")[0] or None)
            or claims.get("sub")
        )

    def get_email(self, claims):
        return claims.get("email", "")

    def get_first_name(self, claims):
        return claims.get("given_name", "") or claims.get("name", "").split(" ")[0]

    def get_last_name(self, claims):
        return claims.get("family_name", "") or " ".join(
            claims.get("name", "").split(" ")[1:]
        )

    # --- user matching ----------------------------------------------------

    def filter_users_by_claims(self, claims):
        email = claims.get("email")
        if email:
            users = self.UserModel.objects.filter(email__iexact=email)
            if users.exists():
                return users
        username = claims.get("preferred_username") or claims.get("username")
        if username:
            return self.UserModel.objects.filter(username=username)
        return self.UserModel.objects.none()

    # --- groups / permissions --------------------------------------------

    def update_groups(self, user, claims):
        raw_groups = claims.get("groups", [])
        if isinstance(raw_groups, str):
            raw_groups = raw_groups.split()

        mapped_groups = [self.GROUP_MAP.get(g) for g in raw_groups]
        mapped_groups = [g for g in mapped_groups if g]

        for name in self.DEFAULT_GROUPS:
            Group.objects.get_or_create(name=name)

        user.groups.set(
            [Group.objects.get_or_create(name=name)[0] for name in mapped_groups]
        )

        self._apply_staff_flag(user, mapped_groups)
        self._apply_base_roast_perms(user)
        self._sync_roasts_group_permissions()

    def _apply_staff_flag(self, user, mapped_groups):
        """Members of STAFF_GROUP become is_staff; non-members are cleared.

        is_superuser is never touched here — that stays a manual admin action.
        """
        should_be_staff = self.STAFF_GROUP in mapped_groups
        if user.is_staff != should_be_staff:
            user.is_staff = should_be_staff
            user.save(update_fields=["is_staff"])

    def _apply_base_roast_perms(self, user):
        """Every authenticated user gets these roasts permissions directly."""
        wanted = Permission.objects.filter(
            content_type__app_label="roasts",
            codename__in=self.BASE_ROAST_PERMS,
        )
        user.user_permissions.add(*wanted)

    def _sync_roasts_group_permissions(self):
        """Keep the 'Coffee Roaster' group scoped to roasts permissions only.

        This is a safety net against accidental grants in the admin UI; the
        actual roasts access for every user comes from _apply_base_roast_perms.
        """
        roaster_group, _ = Group.objects.get_or_create(name=self.STAFF_GROUP)

        roaster_group.permissions.remove(
            *roaster_group.permissions.exclude(
                content_type__app_label="roasts"
            )
        )

        wanted = Permission.objects.filter(
            content_type__app_label="roasts",
            codename__in=self.BASE_ROAST_PERMS,
        )
        roaster_group.permissions.add(*wanted)

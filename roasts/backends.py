from mozilla_django_oidc.auth import OIDCAuthenticationBackend
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType


class CustomOIDCBackend(OIDCAuthenticationBackend):
    # Authentik group name -> Django group name mapping.
    GROUP_MAP = {
        "roast-masters": "Coffee Roaster",
        "roast-viewers": "Viewers",
    }

    # Groups that should exist regardless of who has logged in yet, so admins
    # can attach permissions to them in the Django admin in advance.
    DEFAULT_GROUPS = ("Coffee Roaster", "Viewers")

    def create_user(self, claims):
        user = super().create_user(claims)
        self.update_groups(user, claims)
        return user

    def update_user(self, user, claims):
        user = super().update_user(user, claims)
        self.update_groups(user, claims)
        return user

    def filter_users_by_claims(self, claims):
        """Reuse existing accounts by email (case-insensitive) before falling
        back to username, so pre-OIDC users aren't duplicated."""
        email = claims.get("email")
        if email:
            users = self.UserModel.objects.filter(email__iexact=email)
            if users.exists():
                return users
        username = claims.get("preferred_username") or claims.get("username")
        if username:
            return self.UserModel.objects.filter(username=username)
        return self.UserModel.objects.none()

    def _get_username(self, claims):
        return (
            claims.get("preferred_username")
            or claims.get("username")
            or (claims.get("email", "").split("@")[0] or None)
            or claims.get("sub")
        )

    def _get_email(self, claims):
        return claims.get("email", "")

    def _get_first_name(self, claims):
        return claims.get("given_name", "") or claims.get("name", "").split(" ")[0]

    def _get_last_name(self, claims):
        return claims.get("family_name", "") or " ".join(
            claims.get("name", "").split(" ")[1:]
        )

    def update_groups(self, user, claims):
        raw_groups = claims.get("groups", [])
        if isinstance(raw_groups, str):
            raw_groups = raw_groups.split()

        mapped_groups = [self.GROUP_MAP.get(g) for g in raw_groups]
        mapped_groups = [g for g in mapped_groups if g]  # drop unmapped

        for name in self.DEFAULT_GROUPS:
            Group.objects.get_or_create(name=name)

        user.groups.set(
            [Group.objects.get_or_create(name=name)[0] for name in mapped_groups]
        )

        # Scope permissions to the `roasts` app only.
        self._sync_roasts_permissions(user)

    def _sync_roasts_permissions(self, user):
        """Ensure the 'Coffee Roaster' group has only roasts-app permissions,
        and never staff/admin-level permissions."""
        roaster_group, _ = Group.objects.get_or_create(name="Coffee Roaster")

        # Remove any permissions that don't belong to the roasts app
        # (protects against accidental manual grants).
        roaster_group.permissions.remove(
            *roaster_group.permissions.exclude(
                content_type__app_label="roasts"
            )
        )

        # Grant the roasts permissions we actually want.
        # Adjust this list to match what 'roasts' models/permissions you want:
        # e.g. 'add_roast', 'change_roast', 'delete_roast', 'view_roast'.
        wanted = Permission.objects.filter(
            content_type__app_label="roasts",
            codename__in=[
                "add_roast",
                "change_roast",
                "delete_roast",
                "view_roast",
            ],
        )
        roaster_group.permissions.add(*wanted)

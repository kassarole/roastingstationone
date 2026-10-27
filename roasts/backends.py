from mozilla_django_oidc.auth import OIDCAuthenticationBackend
from django.contrib.auth.models import Group

class CustomOIDCBackend(OIDCAuthenticationBackend):
    def create_user(self, claims):
        user = super().create_user(claims)
        self.update_groups(user, claims)
        return user

    def update_user(self, user, claims):
        user = super().update_user(user, claims)
        self.update_groups(user, claims)
        return user

    def update_groups(self, user, claims):
        # Use 'groups' claim from OIDC token. If missing, default to no groups.
        oidc_groups = claims.get('groups', [])
        
        # Ensure default groups exist
        roaster_group, _ = Group.objects.get_or_create(name='Roasters')
        viewer_group, _ = Group.objects.get_or_create(name='Viewers')
        
        # Clear existing groups and apply from token
        user.groups.clear()
        
        for group_name in oidc_groups:
            group, created = Group.objects.get_or_create(name=group_name)
            user.groups.add(group)
            
        # Example: if they are in the "Roasters" group, give them upload permissions
        # This assumes you have set up custom permissions on the group in the admin.
        # The default Django perms are (add, change, delete, view).
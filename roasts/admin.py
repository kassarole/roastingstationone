from django.contrib import admin
from .models import Roast, RoastEvent, RoastComment, BeanInfo


class EventInline(admin.TabularInline):
    model = RoastEvent
    extra = 0


class CommentInline(admin.TabularInline):
    model = RoastComment
    extra = 0
    fields = ("author", "body", "recommends", "created_at")
    readonly_fields = ("created_at",)


@admin.register(BeanInfo)
class BeanInfoAdmin(admin.ModelAdmin):
    list_display = ("name", "origin", "process", "cultivar", "roast_recommendation")
    list_filter = ("origin", "process")
    search_fields = ("name", "origin", "cultivar")


@admin.register(Roast)
class RoastAdmin(admin.ModelAdmin):
    list_display = (
        "beans", "roast_date", "operator", "origin", "roast_level",
        "weight_in_g", "rating", "owner", "is_public",
    )
    list_filter = ("beans", "roaster_type", "is_public", "roast_level", "origin")
    search_fields = ("beans", "operator", "organization", "title", "origin")
    autocomplete_fields = ("bean_info",) # Adds a search box for linked beans
    readonly_fields = (
        "uuid", "alog_uuid", "uploaded_at", "raw",
        "timex", "temp_bt", "temp_et", "computed",
    )
    inlines = (EventInline, CommentInline)


@admin.register(RoastComment)
class RoastCommentAdmin(admin.ModelAdmin):
    list_display = ("author", "roast", "recommends", "created_at")
    list_filter = ("recommends",)
    search_fields = ("author__username", "body")

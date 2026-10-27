from django.urls import path
from . import views

urlpatterns = [
    path("", views.roast_list, name="roast_list"),
    path("upload/", views.upload, name="roast_upload"),
    path("compare/", views.compare, name="roast_compare"),
    path("stats/", views.stats, name="roast_stats"),
    path("r/<uuid:uuid>/", views.roast_detail, name="roast_detail"),
    path("r/<uuid:uuid>/download/", views.download_alog, name="roast_download"),
    path("r/<uuid:uuid>/claim/", views.claim_ownership, name="roast_claim"),
    path("r/<uuid:uuid>/delete/", views.delete_roast, name="roast_delete"),
    path("r/<uuid:uuid>/meta/", views.update_meta, name="roast_update_meta"),
    path("r/<uuid:uuid>/comment/", views.add_comment, name="roast_comment"),
    path("r/<uuid:uuid>/comment/<int:pk>/delete/", views.delete_comment, name="roast_comment_delete"),
]
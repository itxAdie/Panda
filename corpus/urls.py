from django.urls import path
from corpus import views

app_name = "corpus"
urlpatterns = [
    path("", views.search_page, name="search"),
    path("api/search", views.search_api, name="search_api"),
    path("health", views.health, name="health"),
]

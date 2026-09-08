from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

urlpatterns = [
    path("", views.raiz, name="raiz"),
    path(
        "acceso/",
        auth_views.LoginView.as_view(
            template_name="escuela/login.html",
            redirect_authenticated_user=True,
        ),
        name="login",
    ),
    path("salir/", auth_views.LogoutView.as_view(), name="logout"),
    path("panel/", views.dashboard, name="dashboard"),
    path("padron/", views.padron, name="padron"),
    path("padron/nuevo/", views.alumno_nuevo, name="alumno_nuevo"),
    path("padron/<int:pk>/", views.ficha, name="ficha"),
    path("padron/<int:pk>/editar/", views.alumno_editar, name="alumno_editar"),
    path("padron/<int:pk>/panel/", views.padron_detalle, name="padron_detalle"),
    path("captura/", views.captura, name="captura"),
]

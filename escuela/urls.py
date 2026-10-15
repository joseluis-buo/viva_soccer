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
    path("padron/<int:pk>/baja/", views.alumno_baja, name="alumno_baja"),
    path("padron/<int:pk>/reactivar/", views.alumno_reactivar, name="alumno_reactivar"),
    path("padron/<int:pk>/boleta/", views.boleta, name="boleta"),
    path("padron/<int:pk>/evaluaciones/nueva/", views.evaluacion_nueva, name="evaluacion_nueva"),
    path("evaluaciones/<int:pk>/editar/", views.evaluacion_editar, name="evaluacion_editar"),
    path("evaluaciones/<int:pk>/eliminar/", views.evaluacion_eliminar, name="evaluacion_eliminar"),
    path("boletas/", views.boletas_grupo, name="boletas_grupo"),
    path("tutores/", views.tutores, name="tutores"),
    path("tutores/nuevo/", views.tutor_nuevo, name="tutor_nuevo"),
    path("tutores/<int:pk>/editar/", views.tutor_editar, name="tutor_editar"),
    path("tutores/<int:pk>/eliminar/", views.tutor_eliminar, name="tutor_eliminar"),
    path("captura/", views.captura, name="captura"),
]

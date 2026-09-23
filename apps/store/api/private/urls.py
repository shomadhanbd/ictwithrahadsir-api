from rest_framework.routers import SimpleRouter

from apps.store.api.private.views import AdminProductViewSet

#: No `app_name` -- see the note in the sibling `public/urls.py`.
router = SimpleRouter()
router.register('products', AdminProductViewSet, basename='admin-product')

urlpatterns = router.urls

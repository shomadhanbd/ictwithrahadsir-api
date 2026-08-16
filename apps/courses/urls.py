from rest_framework.routers import SimpleRouter

from django.urls import path

from . import views

# SimpleRouter, not DefaultRouter: every app mounts its own router under
# the same /api prefix, so six DefaultRouters each registered an
# `api-root` view at /api/ and only the first-loaded one ever matched --
# the index advertised one app's routes and hid the other five. Nothing
# consumes the index or the generated `.json` suffix routes.
router = SimpleRouter(trailing_slash=False)
router.register("admin/course-category", views.AdminCourseCategoryViewSet, basename="admin-course-category")
router.register("admin/instructor", views.AdminInstructorViewSet, basename="admin-instructor")
router.register("admin/price", views.AdminCoursePriceViewSet, basename="admin-price")
router.register("admin/coupon", views.AdminCouponViewSet, basename="admin-coupon")
router.register("admin/routine", views.AdminRoutineViewSet, basename="admin-routine")
router.register("admin/section", views.AdminSectionViewSet, basename="admin-section")
router.register("admin/content", views.AdminContentViewSet, basename="admin-content")
router.register("admin/course", views.AdminCourseViewSet, basename="admin-course")

urlpatterns = [
    # Public
    path("courses", views.public_course_list),
    path("courses/<slug:slug>", views.public_course_detail),
    path("course-category", views.public_course_category_list),
    path("content/<slug:slug>", views.content_detail),
    path("content/<slug:slug>/pdf", views.content_pdf),
    path("my-course", views.my_courses),
    # Admin
    path("admin/content/toggle/<int:pk>", views.toggle_content),
    path("admin/course/<int:pk>/users", views.course_enrolled_users),
    path("admin/course/<int:pk>/users/import", views.course_user_import),
    path("admin/course/user-attach", views.course_user_attach),
    path("admin/course/user-update", views.course_user_update),
    path("admin/course/user-remove", views.course_user_remove),
] + router.urls

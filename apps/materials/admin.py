from django.contrib import admin

from apps.materials.models import BookOrder, DeliveryRate, MaterialCategory, MaterialItem, MaterialTopic


@admin.register(MaterialCategory)
class MaterialCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active", "order")
    list_editable = ("is_active", "order")


class MaterialItemInline(admin.TabularInline):
    model = MaterialItem
    extra = 0
    fields = ("order", "kind", "title", "url", "price")


@admin.register(MaterialTopic)
class MaterialTopicAdmin(admin.ModelAdmin):
    list_display = ("title", "category", "access", "is_published", "order")
    list_filter = ("category", "access", "is_published")
    search_fields = ("title",)
    filter_horizontal = ("courses",)
    inlines = (MaterialItemInline,)


@admin.register(DeliveryRate)
class DeliveryRateAdmin(admin.ModelAdmin):
    list_display = ("zone", "charge")


@admin.register(BookOrder)
class BookOrderAdmin(admin.ModelAdmin):
    list_display = ("title", "name", "phone", "zone", "payment", "created_at")
    list_filter = ("zone", "payment__status")
    search_fields = ("name", "phone", "title", "payment__transaction_id")
    readonly_fields = ("payment", "item", "book_price", "delivery_charge")

from django.contrib import admin

from .models import Order, Product, RefundRequest


class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'price', 'in_stock')
    search_fields = ('name', 'category')
    list_filter = ('category', 'in_stock')


class OrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'product_name', 'amount', 'status', 'created_at', 'updated_at')
    search_fields = ('product_name', 'user__username')
    list_filter = ('status', 'created_at')

class RefundRequestAdmin(admin.ModelAdmin):
    list_display = ('id', 'order', 'user', 'reason', 'status', 'created_at', 'updated_at')
    search_fields = ('reason', 'user__username')
    list_filter = ('status', 'created_at')

# Register your models here.
admin.site.register(Product, ProductAdmin)
admin.site.register(Order, OrderAdmin)
admin.site.register(RefundRequest, RefundRequestAdmin)
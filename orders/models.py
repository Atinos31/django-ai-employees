from django.contrib.auth.models import User
from django.db import models

# Create your models here.

class Product(models.Model):
    name= models.CharField(max_length=255)
    description= models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    category= models.CharField(max_length=100)
    in_stock= models.BooleanField(default=True)

    def __str__(self):
        return self.name



class Order(models.Model):
    STATUS_CHOICES = [  # noqa: RUF012
        ('pending', 'Pending'),
        ('dispatched', 'Dispatched'),
        ('delivered', 'Delivered'),
        ('cancelled', 'Cancelled'),
    ]
    user = models.ForeignKey(User, on_delete=models.CASCADE,related_name='orders')
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, related_name='orders')
    product_name = models.CharField(max_length=255)
    quantity = models.PositiveIntegerField(default=1)
    amount = models.DecimalField(max_digits=10, decimal_places=2)  # total paid for this line
    stripe_session_id = models.CharField(max_length=255, blank=True, db_index=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending') 
    carrier = models.CharField(max_length=100, blank=True)
    tracking_number = models.CharField(max_length=100, blank=True)
    delivery = models.TextField(blank=True)
    created_at = models.DateTimeField()#dummy value for created_at field, you can set it to auto_now_add=True if you want it to be automatically set when the object is created
    updated_at = models.DateTimeField(auto_now=True,null=True)

    def __str__(self):
        return f"Order #{self.id} - {self.product_name} - {self.status}"

    

class RefundRequest(models.Model):
    STATUS_CHOICES = [  # noqa: RUF012
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('denied', 'Denied'),
    ]
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='refund_requests')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='refund_requests')
    reason = models.TextField()  # the customer's claim, shown to the customer
    # Internal justification from the Manager Agent or staff. Never shown to customers.
    decision_note = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField()#dummy value for created_at field, you can set it to auto_now_add=True if you want it to be automatically set when the object is created
    updated_at = models.DateTimeField(auto_now=True, null=True)

    def __str__(self):
        return f"Refund Request for Order #{self.order.id} - {self.status}"
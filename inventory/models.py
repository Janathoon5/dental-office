from django.db import models


class SupplyItem(models.Model):
    CATEGORY_CHOICES = [
        ('anesthetics', 'Anesthetics'),
        ('instruments', 'Instruments'),
        ('disposables', 'Disposables'),
        ('materials', 'Dental Materials'),
        ('ppe', 'PPE'),
        ('medications', 'Medications'),
        ('office', 'Office Supplies'),
        ('other', 'Other'),
    ]

    name = models.CharField(max_length=200)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='other')
    quantity = models.PositiveIntegerField(default=0)
    unit = models.CharField(max_length=50, default='units', help_text='e.g. boxes, packs, bottles')
    min_quantity = models.PositiveIntegerField(default=5, help_text='Alert when stock falls below this')
    notes = models.CharField(max_length=200, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['category', 'name']

    def __str__(self):
        return self.name

    def is_low_stock(self):
        return self.quantity <= self.min_quantity

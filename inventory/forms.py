from django import forms

from .models import Product


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ["product_id", "name", "stock", "price", "barcode"]


class SaleForm(forms.Form):
    product = forms.ModelChoiceField(queryset=Product.objects.filter(stock__gt=0))
    quantity = forms.IntegerField(min_value=1, initial=1)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["product"].label_from_instance = (
            lambda p: f"{p.name} ({p.stock} left)"
        )
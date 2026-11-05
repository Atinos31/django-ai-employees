from django.contrib.auth import login
from django.shortcuts import redirect, render

from shop.cart import Cart

from .forms import SignUpForm


def signup(request):
    if request.user.is_authenticated:
        return redirect("orders_list")

    if request.method == "POST":
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)  # keeps the session, so the cart survives
            if Cart(request).count():
                return redirect("cart_detail")
            return redirect("orders_list")
    else:
        form = SignUpForm()

    return render(request, "signup.html", {"form": form})

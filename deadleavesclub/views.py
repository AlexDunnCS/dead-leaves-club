from django.shortcuts import render, redirect
from django.http import HttpResponse
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm

def index(request):
    context = {
        'authentication_failed': False
    }
    if request.user.is_authenticated:
        return redirect('home')
    elif request.method == 'POST':
        login_form = request.POST.get
        username = login_form('username')
        raw_password = login_form('password')
        user = authenticate(username=username, password=raw_password)
        if user:
            login(request, user)
            return redirect('home')
        else:
            context['authentication_failed'] = True
    return render(request, 'deadleavesclub/index.html', context)


def register_user(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            form.save()
            username = form.cleaned_data.get('username')
            raw_password = form.cleaned_data.get('password1')
            user = authenticate(username=username, password=raw_password)
            login(request, user)
            return redirect('home')
    else:
        form = UserCreationForm()
    return render(request, 'deadleavesclub/register.html', {'form': form})


def home(request):
    if request.user.is_authenticated:
        context = {
            'user': request.user
        }
        return render(request, 'deadleavesclub/home.html', context)
    else:
        redirect('index')


def logout_user(request):
    logout(request)
    return redirect('index')

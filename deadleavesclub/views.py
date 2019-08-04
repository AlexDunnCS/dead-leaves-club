from django.shortcuts import render


def index(request):
    return render(request, 'deadleavesclub/index.html', None)

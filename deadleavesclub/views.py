from django.shortcuts import render, redirect


def index(request):
    if request.method == 'POST':
        return redirect('pulogger/newview/?device=test')
    return render(request, 'deadleavesclub/index.html', None)

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from .models import Video
from .forms import VideoForm


@login_required
def video_list(request):
    videos = Video.objects.all()
    can_add = request.user.groups.filter(name='VideoManagers').exists()
    return render(request, 'videos/video_list.html', {
        'videos': videos,
        'can_add': can_add
    })


@login_required
@user_passes_test(lambda u: u.groups.filter(name='VideoManagers').exists())
def video_create(request):
    if request.method == 'POST':
        form = VideoForm(request.POST)
        if form.is_valid():
            video = form.save(commit=False)
            video.created_by = request.user
            video.save()
            messages.success(request, 'Vídeo añadido correctamente')
            return redirect('video_list')
    else:
        form = VideoForm()

    return render(request, 'videos/video_form.html', {'form': form})

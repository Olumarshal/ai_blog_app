from django.shortcuts import render, redirect
from django.contrib.auth.models import User
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from django.conf import settings
import json
from pytube import YouTube
import os
import assemblyai as aai
import openai
from dotenv import load_dotenv
from .models import BlogPost
import logging
from urllib.parse import urlparse

# Load .env file
load_dotenv()

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@login_required
def index(request):
    return render(request, 'index.html')

@csrf_exempt  # Don't do this in production
def generate_blog(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            yt_link = data['link']
        except (KeyError, json.JSONDecodeError):
            return JsonResponse({'error': 'Invalid data sent'}, status=400)

        # get yt title
        title = yt_title(yt_link)

        # get transcript
        transcription = get_transcription(yt_link)
        if not transcription:
            return JsonResponse({'error': 'Failed to get transcript'}, status=500)

        # use OpenAI to generate blog
        blog_content = generate_blog_from_transcription(transcription)
        if not blog_content:
            return JsonResponse({'error': 'Failed to generate blog article'}, status=500)

        # save blog to DB
        new_blog_article = BlogPost.objects.create(
            user=request.user,
            youtube_title=title,
            youtube_link=yt_link,
            generated_content=blog_content
        )
        new_blog_article.save()

        # return blog as response
        return JsonResponse({'content': blog_content})
    else:
        return JsonResponse({'error': 'Invalid request method'}, status=405)

def yt_title(link):
    try:
        yt = YouTube(clean_link(link))
        title = yt.title
        return title
    except Exception as e:
        logger.error(f"Error getting YouTube title: {e}")
        return None

def download_audio(link):
    try:
        yt = YouTube(clean_link(link))
        logger.info(f"Downloading audio for YouTube link: {link}")
        video = yt.streams.filter(only_audio=True).first()
        if not video:
            logger.error("No audio stream found for the provided YouTube link.")
            return None
        out_file = video.download(output_path=settings.MEDIA_ROOT)
        base, ext = os.path.splitext(out_file)
        new_file = base + '.mp3'
        os.rename(out_file, new_file)
        return new_file
    except Exception as e:
        logger.error(f"Error downloading audio: {e}")
        return None

def clean_link(link):
    parsed_url = urlparse(link)
    clean_url = f"{parsed_url.scheme}://{parsed_url.netloc}{parsed_url.path}"
    return clean_url

def get_transcription(link):
    audio_file = download_audio(link)
    if not audio_file:
        return None

    aai.settings.api_key = os.getenv('ASSEMBLY_AI_KEY')
    transcriber = aai.Transcriber()
    try:
        transcript = transcriber.transcribe(audio_file)
        return transcript.text
    except Exception as e:
        logger.error(f"Error transcribing audio: {e}")
        return None

def generate_blog_from_transcription(transcription):
    openai.api_key = os.getenv('OPEN_AI_KEY')
    prompt = f"Based on the following transcript from a YouTube video, write a comprehensive, blog article, write it based on the transcript, but do not make it look like it look like a youtube video, make it look like a proper blog article:\n\n{transcription}\n\nArticle:"
    try:
        response = openai.Completion.create(
            model="text-davinci-003",
            prompt=prompt,
            max_tokens=1000
        )
        generated_content = response.choices[0].text.strip()
        return generated_content
    except Exception as e:
        logger.error(f"Error generating blog from transcription: {e}")
        return None

def user_login(request):
    if request.method == 'POST':
        username = request.POST['username']
        password = request.POST['password']

        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect('/')
        else:
            error_message = 'Invalid Credentials'
            return render(request, 'login.html', {'error_message': error_message})
    return render(request, 'login.html')

def user_signup(request):
    if request.method == 'POST':
        username = request.POST['username']
        email = request.POST['email']
        password = request.POST['password']
        repeatPassword = request.POST['repeatPassword']

        if password == repeatPassword:
            try:
                user = User.objects.create_user(username, email, password)
                user.save()
                login(request, user)
                return redirect('/')
            except Exception as e:
                logger.error(f"Error creating account: {e}")
                error_message = 'Error creating account'
            return render(request, 'signup.html', {'error_message': error_message})
        else:
            error_message = 'Password does not match'
            return render(request, 'signup.html', {'error_message': error_message})
    return render(request, 'signup.html')

def user_logout(request):
    logout(request)
    return redirect('/')

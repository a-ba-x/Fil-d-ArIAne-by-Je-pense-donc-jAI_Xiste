import time
from concurrent.futures import ThreadPoolExecutor
from sound import record_audio
from transcriptGradium import transcribe_audio
import os

def transcript_120(number):
    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs = []

        record_audio("output.wav", duration=5)

        for i in range(23):
            jobs.append(pool.submit(transcribe_audio("output.wav","transcript" + str(number)+ ".txt")))
            record_audio("output.wav", duration=5)
        jobs.append(pool.submit(transcribe_audio("output.wav","transcript" + str(number)+ ".txt")))
    print("Recording and transcription finished.")

#transcript_120()
Going = True

def start():
    i = 0
    for z in range(2):
    #while Going:
        if os.path.exists("transcript" + str(i)+ ".txt"):
            os.remove("transcript" + str(i)+ ".txt")
        transcript_120(i)
        i+=1 
        #with open("settings.txt", encoding="utf-8") as file:
        #    Going = bool(file.read().strip())

start()
import threading
import keyboard
from pynput.keyboard import Key
from threading import Timer
from time import time
import requests
import socketio
import json 
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from spotipy.oauth2 import SpotifyClientCredentials, SpotifyPKCE


# import board
# import neopixel
# import RPi.GPIO as GPIO
# from adafruit_led_animation.animation.pulse import Pulse

#Neopixel Setup
# pixel_pin1 = board.D12 # the pin to which the LED strip is connected to
# pixel_pin2 = board.D10 # the pin to which the ring light is connected to
# num_pixels = 144 # this specifies the TOTAL number of pixels (should be a multiple of 12. ie. 12, 24, 36, 48 etc)
# num_ring_pixels = 16
# ORDER = neopixel.GRBW # set the color type of the neopixel
# ledSegment = 36 # number of LEDs in a single segment
# ledArray = [[[0 for i in range(4)] for j in range(ledSegment)] for z in range(4)] #the array which stores the pixel information

# #Create and initiate neopixel objects
# pixels = neopixel.NeoPixel(pixel_pin1, num_pixels, brightness=0.2, auto_write=False, pixel_order=ORDER)
# ring_pixels = neopixel.NeoPixel(pixel_pin2, num_ring_pixels, brightness = 0.4, auto_write = False, pixel_order=ORDER)

# #Tap Sensor Setup
# channel = 23
# GPIO.setmode(GPIO.BCM)
# GPIO.setup(channel, GPIO.IN, pull_up_down = GPIO.PUD_DOWN)


#variable to determine the client number
clientID=1

#varibale to determine the client state
state=True

#variable that keeps the record of the current BPM added by the user
bpmAdded=36

#both hosted servers for queue player funcitonality
baseUrl="https://qp-master-server.herokuapp.com/"

playerID=""
playing=False
flag=0
bpmCheck=True
count=0
msFirst=0
msPrev=0
seekedPlayer=0
prevDuration=0
colorArrBefore=[(0,0,0,0)]*144
colorArrAfter=[0]*144
prevCheck=True
prevID=' '

#Spotify Library Required Variables
#[OLO5 Credentials]
client_id='765cacd3b58f4f81a5a7b4efa4db02d2'
client_secret='cb0ddbd96ee64caaa3d0bf59777f6871'
spotify_username='n39su59fav4b7fmcm0cuwyv2w'
device_id='1632b74b504b297585776e716b8336510639401a'
spotify_scope='user-library-read,user-modify-playback-state,user-read-currently-playing'
spotify_redirect_uri = 'http://localhost:8000'
sp = spotipy.Spotify(auth_manager=SpotifyOAuth(client_id=client_id, client_secret=client_secret, redirect_uri=spotify_redirect_uri, scope=spotify_scope, username=spotify_username, requests_session=True, requests_timeout=None, open_browser=True))

#function to show the states for each queue player client
def setClientActive():
    global clientID
    setClientActive=requests.post(baseUrl+"setClientActive", json={"clientID":clientID})
    # print("Client States : \n")
    # print(setClientActive.json())

#function to show the states for each queue player client
def setClientInactive():
    global clientID
    setClientInactive=requests.post(baseUrl+"setClientInactive", json={"clientID":clientID})
    # print("Client States : \n")
    # print(setClientInactive.json())

#function to push the BPM added by the client to the master server and use the spotify server to call and play the song if no song is in the queue
#simultaneously update the queue with the pushed BPM
def pushBPMToPlay():
    # print("\nSince Queue was Empty, Pushing song to Play")
    songToBePlayed=requests.post(baseUrl+"getTrackToPlay", json={"bpm":bpmAdded, "clientID":clientID})

    trackArr=[]
    trackArr.append("spotify:track:"+songToBePlayed.json()['song']['track_id'])
    playSong(trackArr)

#function to push the BPM added by the client to the master server
#simultaneously update the queue with the pushed BPM as the player is playing
def pushBPMToQueue():
    # print("\nSince Song is playing, Pushing song to Queue")
    songToBeQueued=requests.post(baseUrl+"getTrackToQueue", json={"bpm":bpmAdded, "userID":clientID})

#function to play the song by sending the request to the spotify server associated with this client
def playSong(trkArr):
    global playerID
    sp.start_playback(device_id=device_id, uris=trkArr)
    sp.volume(100, device_id)   
    global playing
    playing=True

#function to continue playing immediately
def playSongsToContinue(songDuration, songID):
    global playing,prevDuration, prevID
    prevDuration=songDuration
    prevID=songID
    continueSongImmediate=requests.get(baseUrl+"continuePlayingImmediate", json={"userID":clientID})
    trackArr=[]
    trackArr.append("spotify:track:"+continueSongImmediate.json()['song']['track_id'])
    playSong(trackArr)
    playing=True

#function to get the current timestamp playing in all the rest of the players and seek the player 
def seekToPlay():
    global seekedPlayer
    playerSeek=requests.get(baseUrl+"getSeek")
    if(playerSeek.json()['seek']>0):
        # print("Seeked Song")
        # print(playerSeek)
        trackArr=[]
        trackArr.append("spotify:track:"+playerSeek.json()['id'])
        playSong(trackArr)
        seekedPlayer=playerSeek.json()['seek']
        playSongFromSeek()

#function to play the song pointed with the seek timestamp by sending the request to the spotify server associated with this client
def playSongFromSeek():
    global seekedPlayer, device_id
    # print("PlayFromSeek: ", seekedPlayer)
    sp.seek_track(seekedPlayer, device_id)

#function to calculate BPM input
def TapBPM(): 
    global count
    global msFirst  
    global msPrev
    global flag

    msCurr=int(time()*1000)
    if(msCurr-msPrev > 1000*2):
        count = 0

    if(count == 0):
        msFirst = msCurr
        count = 1
    else:
        bpmAvg= 60000 * count / (msCurr-msFirst)
        global bpmAdded
        bpmAdded=round(round(bpmAvg*100)/100)
        # bpmAdded=209
        count+=1 

    msPrev=msCurr
    flag=1

#function to periodically check the client state to indicate when a bpm is added
def checkBPMAdded():    
    global playing,flag, bpmAdded
    msCurr=int(time()*1000)
    if flag==1 and msCurr-msPrev>1000*2:
        if playing:
            pushBPMToQueue()
        else:
            pushBPMToPlay()
        
        flag=0
    
    global bpmCheck
    global bpmTimer
    if bpmCheck:
        bpmTimer=Timer(2,checkBPMAdded)
        bpmTimer.start()
    else:
        bpmTimer.cancel()

def interpolate_rgbw(start_rgbw, end_rgbw, steps):
    r1, g1, b1, w1 = start_rgbw
    r2, g2, b2, w2 = end_rgbw

    delta_r = (r2 - r1) / steps
    delta_g = (g2 - g1) / steps
    delta_b = (b2 - b1) / steps
    delta_w = (w2 - w1) / steps

    results = []
    for i in range(steps + 1):
        r = int(r1 + delta_r * i)
        g = int(g1 + delta_g * i)
        b = int(b1 + delta_b * i)
        w = int(w1 + delta_w * i)
        results.append((r, g, b, w))

    return results

def colorArrayBuilder(lights):
    global colorArrBefore,colorArrAfter
    n=0
    for ring in lights:
        colors=lights[ring]["colors"]
        divs=int(36/len(colors))
        rgb_vals=[]
        for i in colors:
            rgb_vals.append((colors[i]["r"],colors[i]["g"],colors[i]["b"],colors[i]["w"]))
        for i in range(len(rgb_vals)):
            colorArrAfter[n:n+divs]=interpolate_rgbw(rgb_vals[i],rgb_vals[(i+1)%len(rgb_vals)], divs)
            n=n+divs
   
   #Check if color array is different to trigger fade in and out
#    if colorArrBefore != colorArrAfter:
#         # Define the maximum brightness value
#         max_brightness = 255 

#         # Fade-out effect
#         for brightness in range(max_brightness, -1, -1):
#             for i in range (144):
#                 pixels[i] = colorArrBefore[i]
#             #pixels.fill(colorArrBefore)
#             pixels.brightness = brightness / max_brightness
#             pixels.show()
#             time.sleep(0.01)  # Adjust the delay time as desired

#         # Fade-in effect
#         for brightness in range(max_brightness + 1):
#             for i in range (144):
#                 pixels[i] = colorArrAfter[i]
#             #pixels.fill(colorArrAfter)
#             pixels.brightness = brightness / max_brightness
#             pixels.show()
#             time.sleep(0.01)  # Adjust the delay time as desired
    
#         colorArrBefore = copy.deepcopy(colorArrAfter)
        
setClientActive()
seekToPlay()
checkBPMAdded()

print("Press enter for BPM")

# def infiniteloop1(channel):
def infiniteloop1():
    while True:
        value = input()
        if(value==""):
            TapBPM()
        # time.sleep(1)
#     if GPIO.input(channel):
#             print ("Tap")
#             TapBPM()
#     else:
#       print ("No Tap")

# GPIO.add_event_detect(channel, GPIO.BOTH, bouncetime=50)  # let us know when the pin goes HIGH or LOW
# GPIO.add_event_callback(channel, on_tap)  # assign function to GPIO PIN, Run function on change

def infiniteloop2():
    global prevCheck,prevDuration, prevID 
    while True:
        try:    
            currSong=sp.currently_playing()
        except requests.exceptions.ConnectionError:
            print("[Request to SpotifyAPI] Minor Setback, Continue Continue")
            print("ConnectionError: Failed to establish a connection.")
        except requests.exceptions.Timeout:
            print("[Request to SpotifyAPI] Minor Setback, Continue Continue")
            print("Timeout: The request timed out.")
        except requests.exceptions.TooManyRedirects:
            print("[Request to SpotifyAPI] Minor Setback, Continue Continue")
            print("TooManyRedirects: Exceeded maximum redirects.")



        if playing and currSong !=None: 
            if currSong['progress_ms'] != None and currSong['item'] != None:
                if currSong['progress_ms']>0:
                    try:
                        seekData=requests.post(baseUrl+"updateSeek", json={"seek":currSong['progress_ms'], "song":currSong['item']['id']})
                    except requests.exceptions.ConnectionError:
                        print("ConnectionError: Failed to establish a connection.")
                    except requests.exceptions.Timeout:
                        print("Timeout: The request timed out.")
                    except requests.exceptions.TooManyRedirects:
                        print("TooManyRedirects: Exceeded maximum redirects.")

                    if currSong['progress_ms']>10000:
                        if currSong['progress_ms']-10000 > 0 and (prevDuration==currSong['item']['duration_ms'] or prevID==currSong['item']['id']):
                            print("Forcing Continue")
                            playSongsToContinue(currSong['item']['duration_ms'],currSong['item']['id'])
                        if currSong['item']['duration_ms']-currSong['progress_ms'] <= 18000:
                            print("Fading out")
                            currVolume = sp.current_playback()['device']['volume_percent']
                            currVolume=currVolume*0.9
                            sp.volume(int(currVolume), device_id)   
                        if(currSong['progress_ms']+6000>=currSong['item']['duration_ms']):
                            print("Song has ended")
                            # prevCheck=True
                            playSongsToContinue(currSong['item']['duration_ms'],currSong['item']['id'])
                        
                        # if prevCheck:
                        #     prevDuration=currSong['item']['duration_ms']
                        #     prevCheck=False
        else:
            rx=1

thread1 = threading.Thread(target=infiniteloop1)
thread1.start()

thread2 = threading.Thread(target=infiniteloop2)
thread2.start()

sio = socketio.Client()

@sio.event
def connect():
    print('Connected to server')

@sio.event
def disconnect():
    print('Disconnected from server')

@sio.event
def message(data):
    global prevID
    json_data = json.loads(data) # incoming message is transformed into a JSON object
    print("Server Sent the JSON:")
    print(json.dumps(json_data, indent = 2))
    print("///////////////////////////////////////////////////////////////////////////////////////////////////////////")
    if(json_data["msg"]!="Initial"):
        colorArrayBuilder(json_data["lights"])
    global playing
    if playing:
        print(prevID)
        print(json_data["songdata"]["songID"])
        rx=1
    else:
        seekToPlay()

sio.connect('https://qp-master-server.herokuapp.com/')
sio.wait()
    
# while state:
#     # sp.volume(device_id=device, volume=potentionmet)
#     if keyboard.is_pressed("o"):
#         bpmCheck=False
#         setClientInactive()
#         sp.pause_playback(device_id=device_id)
#         print("Client is set Inactive")
#     elif keyboard.is_pressed("s"):
#         bpmCheck=True
#         setClientActive()
#         seekToPlay()
#         checkBPMAdded()
#         print("Client is set Active")



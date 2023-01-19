import threading
from threading import Timer
from time import time
import requests
import websocket #import websockt library -> pip install websocket-client
import ssl # import ssl library (native)
import json # import json library (native)
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import spotipy.util as util
from multipledispatch import dispatch # import the dispatch library to enable method overloading in python
import board
import neopixel
import rel

pixel_pin = board.D21 # the pin to which the LED strip is connected to
num_pixels = 24 # this specifies the TOTAL number of pixels (should be a multiple of 12. ie. 12, 24, 36, 48 etc)
ORDER = neopixel.GRB # set the color type of the neopixel
ledSegment = 6 # number of LEDs in a single segment
ledArray = [[[0 for i in range(3)] for j in range(ledSegment)] for z in range(4)] #the array which stores the pixel information

pixels = neopixel.NeoPixel( # create and initiate neopixel object
    pixel_pin, num_pixels, brightness=0.2, auto_write=False, pixel_order=ORDER
)

#variable to determine the user
userID=2

#variable that keeps the record of the current BPM added by the user
bpmAdded=36

#both hosted servers for queue player funcitonality
base_url="https://qp-master-server.herokuapp.com/"

playerID=""
playing=False
add=0
flag=0
bpmCheck=True
count=0
msFirst=0
msPrev=0
seekedPlayer=0
timeouter=0

#Spotify Library Required Variables
#[OLO4] Credentials
client_id='aeeefb7f628b41d0b7f5581b668c27f4'
client_secret='7a75e01c59f046888fa4b99fbafc4784'
spotify_username='x8eug7lj2opi0in1gnvr8lfsz'
device_id=''
spotify_scope='user-library-read,user-modify-playback-state,user-read-currently-playing'
spotify_redirect_uri = 'https://example.com/callback/'

# sp = spotipy.Spotify(auth_manager=SpotifyOAuth(scope=spotify_scope, client_id=client_id, client_secret=client_secret, redirect_uri=spotify_redirect_uri, username=spotify_username))
token = util.prompt_for_user_token(spotify_username, spotify_scope, client_id = client_id, client_secret = client_secret, redirect_uri = spotify_redirect_uri)
if token:
    sp = spotipy.Spotify(auth=token)

#function to check the active users for each queue player client
def makeUserActive():
    global userID
    userActive=requests.post(base_url+"makeActive", json={"user_id":userID})
    print("Active Users :")
    print(userActive.json())

#function to push the BPM added by the client to the master server and use the spotify server to call and play the song if no song is in the queue
#simultaneously update the queue with the pushed BPM
def pushBPMToPlay():
    print()
    print("Since Queue was Empty, Pushing song to Play")
    songToBePlayed=requests.post(base_url+"getTrackToPlay", json={"bpm":bpmAdded, "userID":userID})
    print("Initial Queue : ", songToBePlayed.json())
    trackArr=[]
    trackArr.append("spotify:track:"+songToBePlayed.json()['song']['track_id'])
    playSong(trackArr)

#function to push the BPM added by the client to the master server
#simultaneously update the queue with the pushed BPM as the player is playing
def pushBPMToQueue(add):
    print()
    print("Since Song is playing, Pushing song to Queue")
    songToBeQueued=requests.post(base_url+"getTrackToQueue", json={"bpm":bpmAdded, "userID":userID, "offset":add})
    print("Updated Queue : ",songToBeQueued.json())

#function to play the song by sending the request to the spotify server associated with this client
def playSong(trkArr):
    global playerID
    print(playerID)
    print()
    print("Playing Song with ID: ", trkArr)
    sp.start_playback(device_id=device_id, uris=trkArr)
    global playing
    playing=True

#function to continue playing the next song from the queue by sending the request to the spotify server associated with this client
# def playSongsToContinue():
#     print()
#     global add,playing, timeouter
#     tc=Timer(1,playSongsToContinue)
#     timeouter+=1
#     print("Continue Playing")
#     print("Timeout Timer: ", timeouter)
#     if(timeouter>=10):
#         continueSongImmediate=requests.get(base_url+"continuePlayingImmediate")
#         trackArr=[]
#         trackArr.append("spotify:track:"+continueSongImmediate.json()['song']['track_id'])
#         add-=1
#         playSong(trackArr)
#         playing=True

#     continueSong=requests.post(base_url+"continuePlaying", json={"user_id":userID})
#     if(timeouter<10 and len(continueSong.json()['queue']) != 0):
#         trackArr=[]
#         trackArr.append("spotify:track:"+continueSong.json()['song']['track_id'])
#         add-=1
#         playSong(trackArr)

#         playing=True

#     if playing:
#         tc.cancel()
#         timeouter=0

#function to continue playing immediately
def playSongsToContinue():
    global add, playing
    continueSongImmediate=requests.get(base_url+"continuePlayingImmediate")
    trackArr=[]
    trackArr.append("spotify:track:"+continueSongImmediate.json()['song']['track_id'])
    add-=1
    playSong(trackArr)
    playing=True

#function to get the current timestamp playing in all the rest of the players and seek the player 
def seekToPlay():
    global seekedPlayer
    playerSeek=requests.get(base_url+"getSeek")
    if(playerSeek.json()['seek']>0):
        print("Seeked Song")
        print(playerSeek)
        trackArr=[]
        trackArr.append("spotify:track:"+playerSeek.json()['id'])
        playSong(trackArr)
        seekedPlayer=playerSeek.json()['seek']
        playSongFromSeek()

#function to play the song pointed with the seek timestamp by sending the request to the spotify server associated with this client
def playSongFromSeek():
    global seekedPlayer, device_id
    print("PlayFromSeek: ", seekedPlayer)
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
        count+=1 

    msPrev=msCurr
    flag=1

#function to periodically check the client state to indicate when a bpm is added
def checkBPMAdded():    
    global playing, add, flag, bpmAdded
    msCurr=int(time()*1000)
    if flag==1 and msCurr-msPrev>1000*2:
    # if flag==1:
        if playing:
            add+=1
            pushBPMToQueue(add)
        else:
            pushBPMToPlay()
        
        flag=0
    
    global bpmCheck
    if bpmCheck:
        Timer(2,checkBPMAdded).start()

makeUserActive()
seekToPlay()
checkBPMAdded()

print("Press enter for BPM")

def infiniteloop1():
    while True:
        value = input()
        if(value==""):
            TapBPM()
        # time.sleep(1)

def infiniteloop2():
    while True:
        websocket.enableTrace(True) # print the connection details (for debugging purposes)
        ws = websocket.WebSocketApp("wss://qp-master-server.herokuapp.com/", # websocket URL to connect to
            on_message = on_message, # what should happen when we receive a new message
            on_error = on_error, # what should happen when we get an error
            on_close = on_close, # what should happen when the connection is closed
            on_ping = on_ping, # on ping
            on_pong = on_pong) # on pong
        ws.on_open = on_open # call on_open function when the ws connection is opened
        ws.run_forever(dipatcher=rel, reconnect=5, ping_interval=15, ping_timeout=10, ping_payload="This is an optional ping payload", sslopt={"cert_reqs": ssl.CERT_NONE}) # run code forever and disable the requirement of SSL certificates
        rel.signal(2, rel.abort) # keyboard interrupt
        rel.dispatch()

def on_message(ws, message): # function which is called whenever a new message comes in
    json_data = json.loads(message) # incoming message is transformed into a JSON object
    print("")
    print("Server Sent the JSON:")
    print(message) # printing the data (for testing purposes)
    updatePixels(json_data) # call function to update neopixel strip
    print("") # printing new line for better legibility

def on_error(ws, error): # function call when there is an error
    print("got an error: ", error)

def on_close(ws, e, d): # function call when the connection is closed (this should not happend currently as we are staying connected)
    print("### closed ###")
    print(e)
    print(d)

def on_ping(wsapp, message):
    print("Got a ping! A pong reply has already been automatically sent. ", message)

def on_pong(wsapp, message):
    print("Got a pong! No need to respond. ", message)
    
def on_open(ws): # function call when a new connection is established
    print("### open ###")

def updatePixels(json):
    iteration = 0 # reset number of iterations to 0. this is a helper variable to address different segments of the LED strip
    for ring in json["lights"]: # iterate through every ring object inside the JSON file

        l = len(json["lights"][ring]["colors"]) # figure out how many colors should be displayed
        if l == 1: # if one light needs to be displayed
            c1r = json["lights"][ring]["colors"]["1"]["r"] # get the red color value
            c1g = json["lights"][ring]["colors"]["1"]["g"] # get the green color value
            c1b = json["lights"][ring]["colors"]["1"]["b"] # get the blue color value
            
            setColorArray(iteration,c1r,c1g,c1b) # call the setColorArray function

        elif l == 2: # if two lights need to be displayed (gradient)
            c1r = json["lights"][ring]["colors"]["1"]["r"] # get the first red color value
            c1g = json["lights"][ring]["colors"]["1"]["g"] # get the first green color value
            c1b = json["lights"][ring]["colors"]["1"]["b"] # get the first blue color value

            c2r = json["lights"][ring]["colors"]["2"]["r"] # get the second red color value
            c2g = json["lights"][ring]["colors"]["2"]["g"] # get the second green color value
            c2b = json["lights"][ring]["colors"]["2"]["b"] # get the second blue color value
            
            setColorArray(iteration,c1r,c1g,c1b,c2r,c2g,c2b) # call the setColorArray function

        elif l == 3: # if three lights need to be displayed (gradient)
            c1r = json["lights"][ring]["colors"]["1"]["r"] # get the first red color value
            c1g = json["lights"][ring]["colors"]["1"]["g"] # get the first green color value
            c1b = json["lights"][ring]["colors"]["1"]["b"] # get the first blue color value

            c2r = json["lights"][ring]["colors"]["2"]["r"] # get the second red color value
            c2g = json["lights"][ring]["colors"]["2"]["g"] # get the second green color value
            c2b = json["lights"][ring]["colors"]["2"]["b"] # get the second blue color value
            
            c3r = json["lights"][ring]["colors"]["3"]["r"] # get the third red color value
            c3g = json["lights"][ring]["colors"]["3"]["g"] # get the third green color value
            c3b = json["lights"][ring]["colors"]["3"]["b"] # get the third blue color value
            
            setColorArray(iteration,c1r,c1g,c1b,c2r,c2g,c2b,c3r,c3g,c3b) # call the setColorArray function

        elif l == 4: # if four lights need to be displayed (gradient)
            c1r = json["lights"][ring]["colors"]["1"]["r"] # get the first red color value
            c1g = json["lights"][ring]["colors"]["1"]["g"] # get the first green color value
            c1b = json["lights"][ring]["colors"]["1"]["b"] # get the first blue color value
            
            c2r = json["lights"][ring]["colors"]["2"]["r"] # get the second red color value
            c2g = json["lights"][ring]["colors"]["2"]["g"] # get the second green color value
            c2b = json["lights"][ring]["colors"]["2"]["b"] # get the second blue color value
            
            c3r = json["lights"][ring]["colors"]["3"]["r"] # get the third red color value
            c3g = json["lights"][ring]["colors"]["3"]["g"] # get the third green color value
            c3b = json["lights"][ring]["colors"]["3"]["b"] # get the third blue color value
            
            c4r = json["lights"][ring]["colors"]["3"]["r"] # get the fourth red color value
            c4g = json["lights"][ring]["colors"]["3"]["g"] # get the fourth green color value
            c4b = json["lights"][ring]["colors"]["3"]["b"] # get the fourth blue color value
            
            setColorArray(iteration,c1r,c1g,c1b,c2r,c2g,c2b,c3r,c3g,c3b,c4r,c4g,c4b) # call the setColorArray function
        
        offset = iteration * ledSegment # calculate the offset to address the single neopixel strip as it were N number of strips

        for index in range(ledSegment): # for loop to run through the individual segments
            pixels[index+offset] = (ledArray[iteration][index][0],ledArray[iteration][index][1],ledArray[iteration][index][2]) # for each pixel on the LED strip, calculate the position of the color inside the three dimensional color array and assign it
        
        iteration += 1 # increase the iteration (ie. work on the next segment of the LED strip)
    
    pixels.show() # once done, update the led strip

# function to assign single color to array
@dispatch(int, int, int, int)
def setColorArray(iteration, c1r, c1g, c1b):
    for x in range(ledSegment): # cycle through the whole segment
        ledArray[iteration][x][0] = c1r # set the value of the red channel to the whole color array
        ledArray[iteration][x][1] = c1g # set the value of the green channel to the whole color array
        ledArray[iteration][x][2] = c1b # set the value of the blue channel to the whole color array

# function to assign two colors to array to create a gradient
@dispatch(int, int, int, int, int, int, int)
def setColorArray(iteration, c1r, c1g, c1b, c2r, c2g, c2b):
    for x in range(int(ledSegment/2)): # cycle through half of the segment (as we need to create a gradient, the other half of the segment is automatically calculated)
        ledArray[iteration][x + ((int(ledSegment/2))*0)][0] = int((x - 0) / ((int(ledSegment/2)) - 0) * (c2r - c1r) + c1r) # based on the position inside the color array, calculate the value of the red channel so it morphs from the first color to the second
        ledArray[iteration][x + ((int(ledSegment/2))*1)][0] = int((x - 0) / ((int(ledSegment/2)) - 0) * (c1r - c2r) + c2r)

        ledArray[iteration][x + ((int(ledSegment/2))*0)][1] = int((x - 0) / ((int(ledSegment/2)) - 0) * (c2g - c1g) + c1g) # based on the position inside the color array, calculate the value of the green channel so it morphs from the first color to the second
        ledArray[iteration][x + ((int(ledSegment/2))*1)][1] = int((x - 0) / ((int(ledSegment/2)) - 0) * (c1g - c2g) + c2g)

        ledArray[iteration][x + ((int(ledSegment/2))*0)][2] = int((x - 0) / ((int(ledSegment/2)) - 0) * (c2b - c1b) + c1b) # based on the position inside the color array, calculate the value of the blue channel so it morphs from the first color to the second
        ledArray[iteration][x + ((int(ledSegment/2))*1)][2] = int((x - 0) / ((int(ledSegment/2)) - 0) * (c1b - c2b) + c2b)

# function to assign three colors to array to create a gradient
@dispatch(int, int, int, int, int, int, int, int, int, int)
def setColorArray(iteration, c1r, c1g, c1b, c2r, c2g, c2b, c3r, c3g, c3b):
    for x in range(int(ledSegment/3)): # cycle through a third of the segment (as we need to create a gradient, the other two thirds of the segment are automatically calculated)
        ledArray[iteration][x + ((int(ledSegment/3))*0)][0] = int((x - 0) / ((int(ledSegment/3)) - 0) * (c2r - c1r) + c1r) # based on the position inside the color array, calculate the value of the red channel so it morphs from the first color to the second and to the third
        ledArray[iteration][x + ((int(ledSegment/3))*1)][0] = int((x - 0) / ((int(ledSegment/3)) - 0) * (c3r - c2r) + c2r)
        ledArray[iteration][x + ((int(ledSegment/3))*2)][0] = int((x - 0) / ((int(ledSegment/3)) - 0) * (c1r - c3r) + c3r)

        ledArray[iteration][x + ((int(ledSegment/3))*0)][1] = int((x - 0) / ((int(ledSegment/3)) - 0) * (c2g - c1g) + c1g) # based on the position inside the color array, calculate the value of the green channel so it morphs from the first color to the second and to the third
        ledArray[iteration][x + ((int(ledSegment/3))*1)][1] = int((x - 0) / ((int(ledSegment/3)) - 0) * (c3g - c2g) + c2g)
        ledArray[iteration][x + ((int(ledSegment/3))*2)][1] = int((x - 0) / ((int(ledSegment/3)) - 0) * (c1g - c3g) + c3g)

        ledArray[iteration][x + ((int(ledSegment/3))*0)][2] = int((x - 0) / ((int(ledSegment/3)) - 0) * (c2b - c1b) + c1b) # based on the position inside the color array, calculate the value of the blue channel so it morphs from the first color to the second and to the third
        ledArray[iteration][x + ((int(ledSegment/3))*1)][2] = int((x - 0) / ((int(ledSegment/3)) - 0) * (c3b - c2b) + c2b)
        ledArray[iteration][x + ((int(ledSegment/3))*2)][2] = int((x - 0) / ((int(ledSegment/3)) - 0) * (c1b - c3b) + c3b)

# function to assign four colors to array to create a gradient
@dispatch(int, int, int, int, int, int, int, int, int, int, int, int, int)
def setColorArray(iteration, c1r, c1g, c1b, c2r, c2g, c2b, c3r, c3g, c3b, c4r, c4g, c4b):
    for x in range(int(ledSegment/4)):  # cycle through a fourth of the segment (as we need to create a gradient, the other three quarters of the segment are automatically calculated)
        ledArray[iteration][x + ((int(ledSegment/4))*0)][0] = int((x - 0) / ((int(ledSegment/4)) - 0) * (c2r - c1r) + c1r) # based on the position inside the color array, calculate the value of the red channel so it morphs from the first color to the second, to the third, and to the fourth
        ledArray[iteration][x + ((int(ledSegment/4))*1)][0] = int((x - 0) / ((int(ledSegment/4)) - 0) * (c3r - c2r) + c2r)
        ledArray[iteration][x + ((int(ledSegment/4))*2)][0] = int((x - 0) / ((int(ledSegment/4)) - 0) * (c4r - c3r) + c3r)
        ledArray[iteration][x + ((int(ledSegment/4))*3)][0] = int((x - 0) / ((int(ledSegment/4)) - 0) * (c1r - c4r) + c4r)

        ledArray[iteration][x + ((int(ledSegment/4))*0)][1] = int((x - 0) / ((int(ledSegment/4)) - 0) * (c2g - c1g) + c1g) # based on the position inside the color array, calculate the value of the green channel so it morphs from the first color to the second, to the third, and to the fourth
        ledArray[iteration][x + ((int(ledSegment/4))*1)][1] = int((x - 0) / ((int(ledSegment/4)) - 0) * (c3g - c2g) + c2g)
        ledArray[iteration][x + ((int(ledSegment/4))*2)][1] = int((x - 0) / ((int(ledSegment/4)) - 0) * (c4g - c3g) + c3g)
        ledArray[iteration][x + ((int(ledSegment/4))*3)][1] = int((x - 0) / ((int(ledSegment/4)) - 0) * (c1g - c4g) + c4g)

        ledArray[iteration][x + ((int(ledSegment/4))*0)][2] = int((x - 0) / ((int(ledSegment/4)) - 0) * (c2b - c1b) + c1b) # based on the position inside the color array, calculate the value of the blue channel so it morphs from the first color to the second, to the third, and to the fourth
        ledArray[iteration][x + ((int(ledSegment/4))*1)][2] = int((x - 0) / ((int(ledSegment/4)) - 0) * (c3b - c2b) + c2b)
        ledArray[iteration][x + ((int(ledSegment/4))*2)][2] = int((x - 0) / ((int(ledSegment/4)) - 0) * (c4b - c3b) + c3b)
        ledArray[iteration][x + ((int(ledSegment/4))*3)][2] = int((x - 0) / ((int(ledSegment/4)) - 0) * (c1b - c4b) + c4b)        
    
def infiniteloop3():
    while True:
        if playing:
            if sp.currently_playing()['progress_ms']>0 and sp.currently_playing()['item']['id'] != None:
                seekData=requests.post(base_url+"updateSeek", json={"seek":sp.currently_playing()['progress_ms'], "song":sp.currently_playing()['item']['id']})
            if sp.currently_playing()['progress_ms']>10000:
                if(sp.currently_playing()['progress_ms']+10000>=sp.currently_playing()['item']['duration_ms']):
                    print("Song has ended")
                    playSongsToContinue()

    
thread1 = threading.Thread(target=infiniteloop1)
thread1.start()

thread2 = threading.Thread(target=infiniteloop2)
thread2.start()

thread3 = threading.Thread(target=infiniteloop3)
thread3.start()



#TODO : Coordinate rotation bug
import numpy
import cv2
from picamera.array import PiRGBArray
from picamera import PiCamera
import time
from networktables import NetworkTable
import pistream
import sys
import math


# if running from command line, passing any value as a parameter will
# stop the image windows from being displayed.
if len(sys.argv) > 1:  #python filename is always in arg list, so look for 2 or more
    showImages = False
else:
    showImages = True

#robot shop
#LOWER_HSV = numpy.array([57,206,30])
#UPPER_HSV = numpy.array([105,255,255])
#Gym
#LOWER_HSV = numpy.array([30,23,50])
#UPPER_HSV = numpy.array([104,255,220])
#At Pine Tree
#LOWER_HSV = numpy.array([49,26,112])
#UPPER_HSV = numpy.array([94,255,226])
# Camera with Exposure in Night mode
#LOWER_HSV = numpy.array([45,162,130])
#UPPER_HSV = numpy.array([78,255,255])
LOWER_HSV = numpy.array([43,113,130])
UPPER_HSV = numpy.array([99,255,255])

#These constants control goal detection values

#Parameters for robot turning speed
TURN_SCALE = 0.011           #Multiplier to determine turn rate, given error from center in pixels that will determine the robot turn rate
TURN_MAX_RATE = 0.9        #Fastest turn rate allowed
TURN_MIN_RATE = 0.55      #was .7 Slowest turn rate allowed

# Setup PiCamera for capture
# IMG_WIDTH = 240
# IMG_HEIGHT = 180
IMG_WIDTH = 640
IMG_HEIGHT = 360
video = pistream.PiVideoStream((IMG_WIDTH,IMG_HEIGHT)).start()
time.sleep(2)  #Give camera a chance to stablize

MINIMUM_ALIGN_DISTANCE = 20


# Connect to roboRio via NetworkTable
NetworkTable.setIPAddress("10.45.64.2")
NetworkTable.setClientMode()
NetworkTable.initialize()

table = NetworkTable.getTable("visionTracking")

def dst2errorX(TargetCenter, Distance) :
    # theta = math.atan(TargetCenter/581.4)
    theta = math.atan(TargetCenter/622.7722)
    return Distance*math.sin(theta)

def calcRoboAngle(x,y) :
    if x == 0 :
        return 1000000 ,0
    x = 2*x
    a = y/math.sqrt(abs(x)) - MINIMUM_ALIGN_DISTANCE
    # angle = math.atan((a/(2*math.sqrt(abs(x))))*(x/abs(x)))
    angle = math.atan((a/(2*math.sqrt(abs(x)))))
    d_angle = -a/4*(abs(x)**(-3/2.0))
    d_angle = d_angle*x/abs(x)
    d_angle = math.atan(d_angle)*math.pi/2
    return angle, d_angle

def pos2tempArc(x,y) :
    a = y/math.sqrt(abs(x)) - MINIMUM_ALIGN_DISTANCE



# Process images continuously, outputting a comamnd to the robot each cycle
def process():
    # Init contour measurements for picture saving
    h = 0
    w = 0
    center = 0
    imageCounter = 0  #Counter for filename of saved images

    kernel = numpy.ones((3,3),
                        numpy.uint8)  #used to do dialate

    dist = [0.0,0.0]
    angle = 0.0 # target angle in degrees
    fps = 0
    a = 0

    while True:
        startTime = time.time()

        # Grab frame from PiCamera
        img_bgr = video.read()

        # Resize to a smaller image for better performance
        img_bgr = cv2.resize(img_bgr, (IMG_WIDTH,IMG_HEIGHT),interpolation = cv2.INTER_LINEAR)


        img_hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)

        # Create a binary threshold based on the HSV range (look for green reflective tape)
        img_thresh = cv2.inRange(img_hsv, LOWER_HSV, UPPER_HSV)
        if showImages:
            cv2.imshow("img_thresh",img_thresh)

        # Dilate them image to fill holes
        img_dialate = cv2.dilate(img_thresh, kernel, iterations=1)

        if showImages:
            cv2.imshow("img_dialate",img_dialate)

        # Find all of the contours in binary image
        _, contours, _ = cv2.findContours(img_dialate, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

        # Now we'll evaluate the contours.
        # We'll assume that no goal is visible at first.
        # The value of 'turn' will indicate what action the robot should take.
        # 0=no goal, do nothing, 999=aligned with goal, shoot, +/-x.xxx=turn rate to move to target
        turn = 0
        okCount = 0
        j = 0
        OkCountours = [0,0,0,0,0,0,0,0]
        if len(contours) > 0:
            #Check all contours, or until we see one that looks like a goal
            for c in contours:
                # Is the contour big enough to be a goal?
                area = cv2.contourArea(c) # area of rectangle that is filled
                x,y,w,h = cv2.boundingRect(c)
                ratio = float(h) / float(w)
                ratioError = ratio-5.0/2.0
                if abs(ratioError) < 2.0 and  w*h > 30:
                    center = x + (w/2)
                    # print h,w,area,center,turn
                    if okCount > 4:
                        print "Too much contours"
                        break

                    OkCountours[okCount] = j
                    okCount = okCount + 1
                j = j +1
        else:
            print "No contours found"
            turn = 0
        # print "RatioOkCount:",okCount
        i = 0
        markercount = 0
        while  okCount> i+1:
            x,y,w,h = cv2.boundingRect(contours[OkCountours[i]])
            j = 0
            while i+j < okCount :
                x_p,y_p,w_p,h_p = cv2.boundingRect(contours[OkCountours[i+j]])
                if abs(abs(float(x - x_p) / ((h+h_p)/2.0))-(8.25/5.0)) < 1.0 and abs(y_p-y) < 15 and abs(h-h_p) < 10  :
                    #Calculate position of each target
                    dist = [5*773.5/h, 5*773.5/h_p] #calculate distance based upon height of marker
                    Xr = [dst2errorX((x+(w/2.0))-IMG_WIDTH/2, dist[0]),dst2errorX((x_p+(w_p/2.0))-IMG_WIDTH/2, dist[1])]
                    Yr = [math.sqrt(dist[0]*dist[0]-Xr[0]*Xr[0]),math.sqrt(dist[1]*dist[1]-Xr[1]*Xr[1])]
                    angle = math.pi - math.atan((Yr[1]-Yr[0])/(Xr[1]-Xr[0]))
                    Xm = [Xr[0]*math.cos(angle)-Yr[0]*math.sin(angle),Xr[1]*math.cos(angle)-Yr[1]*math.sin(angle)]
                    Ym = [-Xr[0]*math.sin(angle)-Yr[0]*math.cos(angle),-Xr[1]*math.sin(angle)-Yr[1]*math.cos(angle)]
                    RoboAngle, dRoboAngle= calcRoboAngle((Xm[0]+Xm[1])/2.0,(Ym[0]+Ym[1])/2.0)
                    # print "TargetAngle :" , round(math.degrees(angle-RoboAngle-math.pi/2),3)
                    angle = h-h_p
                    if abs(angle) > 5 :
                        angle = 5*angle/abs(angle)
                    slideRate = (Xr[0]+Xr[1])/2.0
                    slideRate = slideRate/20
                    if abs(slideRate) > 1 :
                        angle = slideRate/abs(slideRate)
                    markercount = markercount+1
                    print angle, slideRate, (Yr[0]+Yr[1])/2.0
                    if (Xm[0]+Xm[1]) < 0 :
                        RoboAngle = -RoboAngle-math.pi
                    # print "Height :",h,h_p , \
                    # "TargetCenter :",x+w/2.0 - IMG_WIDTH/2, \
                    # "Distance :", dist[0], \
                    # "Markers",okCount ,\
                    # "X :" , Xr[0], \
                    # "Y :" , Yr[0] ,\
                    # "TargetAngle :" , round(math.degrees(angle-RoboAngle-3*math.pi/2.0),3), math.degrees(dRoboAngle) ,\
                    # "FPS :" , int(fps)
                    cv2.circle(img_bgr,(int((x+x_p+(w_p+w)/2.0)/2.0),int(((y+y_p)/2.0)+(h+h_p)/4.0)),3,(0,0,255), -1)
                    # cv2.circle(img_bgr,int((x+w/2)),int((y+h/2)),3,(0,255,0), -1)
                    # cv2.circle(img_bgr,int((x_p+w_p/2)),int((y_p+h_p/2)),3,(255,0,0), -1)
                    break
                j = j +1
            i = i+1


        if showImages:
            cv2.imshow("img_bgr",img_bgr)


        if markercount == 1 :
            table.putNumber("distance", (Yr[0]+Yr[1])/2.0)
            table.putNumber("slideInces", (Xr[0]+Xr[1])/2.0)
            table.putNumber("rateTurn" , angle)
        else :
            table.putNumber("targetTurn", 999)
        table.putNumber("distance",(dist[0]+dist[1])/2.0)

        # Check to see if robot wants us to save a picture
        try:
            takePicture = table.getNumber("takePicture")
        except:
            takePicture = 0

        try:
            if takePicture == 1:
                print "Saving picture"
                # Print width, height ,center, turn on image
                text = "w"+str(w)+" h"+str(h)+" c"+str(center)+" t"+str(turn)
                cv2.putText(img_bgr,text,(1,150),cv2.FONT_HERSHEY_SIMPLEX,.35,(255,255,255),1)
                # Save image
                cv2.imwrite("/home/pi/vision/captures/image" + str(imageCounter) + ".jpg", img_bgr, [cv2.IMWRITE_JPEG_QUALITY, 90])
                imageCounter += 1
                print "Image saved"
                table.putNumber("takePicture",0)
        except:
            print "Failed to take picture"
            raise
            table.putNumber("takePicture",0)

        # Wait 1ms for keypress. q to quit.
        if cv2.waitKey(1) &0xFF == ord('q'):
            break

        fps = 1.0/(time.time()-startTime)


# Process until user exit (q or ctrl-c)
try:
    process()
# Always clean up before exit
finally:
    video.stop()
    cv2.destroyAllWindows()
import math, datetime, numpy as np
from astral import LocationInfo
from astral.sun import azimuth, elevation
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

def compute_sun_vector(lat,lon):
    now=datetime.datetime.now(datetime.timezone.utc)
    city=LocationInfo(latitude=lat,longitude=lon)
    az=azimuth(city.observer,now); el=elevation(city.observer,now)
    azr,elr=math.radians(az),math.radians(el)
    return math.cos(elr)*math.sin(azr), math.cos(elr)*math.cos(azr), math.sin(elr)

def draw_device_orientation(ax,roll,pitch,yaw,lat,lon):
    ax.cla(); ax.set_xlim([-3,3]); ax.set_ylim([-3,3]); ax.set_zlim([-3,3])
    s=0.2; cube=np.array([[-s,-s,-s],[s,-s,-s],[s,s,-s],[-s,s,-s],[-s,-s,s],[s,-s,s],[s,s,s],[-s,s,s]])
    rx=[[1,0,0],[0,math.cos(math.radians(roll)),-math.sin(math.radians(roll))],[0,math.sin(math.radians(roll)),math.cos(math.radians(roll))]]
    ry=[[math.cos(math.radians(pitch)),0,math.sin(math.radians(pitch))],[0,1,0],[-math.sin(math.radians(pitch)),0,math.cos(math.radians(pitch))]]
    rz=[[math.cos(math.radians(yaw)),-math.sin(math.radians(yaw)),0],[math.sin(math.radians(yaw)),math.cos(math.radians(yaw)),0],[0,0,1]]
    rc=(np.array(rz)@np.array(ry)@np.array(rx)@cube.T).T
    edges=[[rc[0],rc[1],rc[2],rc[3]],[rc[4],rc[5],rc[6],rc[7]],[rc[0],rc[1],rc[5],rc[4]],[rc[2],rc[3],rc[7],rc[6]],[rc[1],rc[2],rc[6],rc[5]],[rc[4],rc[7],rc[3],rc[0]]]
    for e in edges: ax.add_collection3d(Poly3DCollection([e],facecolors='#ccc',edgecolors='k',alpha=0.2))
    sx,sy,sz=compute_sun_vector(lat,lon); ax.scatter([sx],[sy],[sz],s=50)


try:
    import libscrc
    def modbus_crc16(data: bytes) -> int:
        return libscrc.modbus(data)
except ImportError:
    def modbus_crc16(data: bytes) -> int:
        crc = 0xFFFF
        for b in data:
            crc ^= b
            for _ in range(8):
                if crc & 1:
                    crc = (crc >> 1) ^ 0xA001
                else:
                    crc >>= 1
        return crc & 0xFFFF
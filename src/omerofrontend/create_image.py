import omero
import ezomero
import omero.rtypes
from . import conf
from . import logger
#from threading import Lock
from PIL import Image
import numpy as np
from . import omero_connection


def create_image_and_file(file, omeroconn):
    conn = omeroconn.get_omero_connection()

    session = conn.getSession()

    # Access the service factory
    service_factory = session.Factory()

    # Get the ImportService
    import_service = service_factory.getImportService()



    orig_file = conn.createOriginalFileFromLocalFile(
        localPath=file,
        mimetype="application/octet-stream",
        ns=""#,
        #name=file
        )

    # Upload the file
    # raw_file_store = conn.createRawFileStore()
    # id = orig_file.getId()
    # #val = id.getValue()
    # raw_file_store.setFileId(id)
    
    # with open(file, "rb") as f:
    #     buf = f.read(2621440)  # 2.5 MB chunks
    #     while buf:
    #         raw_file_store.write(buf, length=len(buf))
    #         buf = f.read(2621440)
    
    # raw_file_store.close()

    # Create an image from the original file
    image = conn.createImageFromNumpySeq(
        #plane2D=None,
        imageName=file,
        sizeZ=1, sizeT=1,
#        dataset=dataset,
        sourceImageId=id
    )

    print(f"Image uploaded with ID: {image.getId()}")


def create_omero_file(file, omeroconn):
    f = omeroconn.get_omero_connection().createOriginalFileFromLocalFile(file,mimetype="text/plain")
    f.save()
    return

def create_omero_image(file, omeroconn):

    im = Image.open(file)
    im2arr = np.array(im) # im2arr.shape: height x width x channel
    #arr2im = Image.fromarray(im2arr) original = conn.getObject("Image", 1)
    sizeZ = 1#original.getSizeZ()
    sizeC = 1#original.getSizeC()
    sizeT = 1# original.getSizeT()
    clist = range(sizeC)
    zctList = []
    for z in range(sizeZ):
        for c in clist:
            for t in range(sizeT):
                zctList.append( (z,c,t) )
    def planeGen():
        yield im2arr
        #planes = original.getPrimaryPixels().getPlanes(zctList)
        #for p in planes:
            # perform some manipulation on each plane
       #     yield p
    img = omeroconn.get_omero_connection().createImageFromNumpySeq(
            planeGen(), file, sizeZ=sizeZ, sizeC=sizeC, sizeT=sizeT,
            channelList=clist)
    
    img.save()
    return

conn = omero_connection.OmeroConnection("130.241.39.241",'4064','0c61313c-2fb5-44ff-883a-be60681b9fac')
#create_omero_image("testimage.png",conn)
#create_omero_file("testimage.czi",conn)
#create_omero_file("requirements.txt",conn)
create_image_and_file("image.tif",conn)
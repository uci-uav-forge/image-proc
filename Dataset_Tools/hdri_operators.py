# Blender imports
import bpy.types

# Other imports
import numpy as np
from math import pi, cos, sin
import mathutils


def rotate(context):
    """Rotate active object in alignment with sun position"""     

    bl_idname = "hdrisa.rotate"     
    bl_label = "Rotate active object in alignment with sun position."         
    bl_options = {'REGISTER'}


    def execute(context):
        scene = context.scene
        object = bpy.data.objects['HDRI Sun']
  
        longitude = scene.hdri_sa_props.long_deg * (pi/180) # Convert to radians
        latitude = scene.hdri_sa_props.lat_deg * (pi/180)

        # Calculate a vector pointing from the longitude and latitude to origo
        # See https://vvvv.org/blog/polar-spherical-and-geographic-coordinates 
        x = cos(latitude) * cos(longitude)
        y = cos(latitude) * sin(longitude)
        z = sin(latitude)

        # Define euler rotation according to the vector
        vector = mathutils.Vector([x, -y, z]) # "-y" to match Blender coordinate system
        up_axis = mathutils.Vector([0.0, 0.0, 1.0])
        angle = vector.angle(up_axis, 0)
        axis = up_axis.cross(vector)
        euler = mathutils.Matrix.Rotation(angle, 4, axis).to_euler()

        # Store z-rotation value as property, used for driver calculation 
        scene.hdri_sa_props.z_org = euler.z
        
        # Rotate selected object
        object.rotation_euler = euler
        
        return {'FINISHED'}   

    execute(context)


def add_new_sun(context):
    """Add a new sun, rotated in alignment with current sun position"""     

    bl_idname = "hdrisa.add_new_sun"     
    bl_label = "Add a new sun, rotated in alignment with current sun position."         
    bl_options = {'REGISTER'}

    def make_collection(collection_name):
        # Check if collection already exists
        if collection_name in bpy.data.collections:
            return bpy.data.collections[collection_name]
        # If not, create new collection
        else:
            new_collection = bpy.data.collections.new(collection_name)
            bpy.context.scene.collection.children.link(new_collection)
            return new_collection

    def execute(context):
        # Deselect objects
        for obj in context.selected_objects:
            obj.select_set(state=False)
        
        # Create new collection if it doesn't exist        
        new_collection = make_collection("HDRI Sun Aligner")
        
        # Create new sun object in the collection
        sun_data = bpy.data.lights.new(name="HDRI Sun", type='SUN')
        sun_object = bpy.data.objects.new(name="HDRI Sun", object_data=sun_data)
        new_collection.objects.link(sun_object)
        
        # Select sun object and rotate
        sun_object.select_set(state=True)
        context.view_layer.objects.active = sun_object
        rotate(context)

        return {'FINISHED'}

    execute(context)

    


def add_rotation_driver(context):
    """Add a a driver to the active object z-rotation, based on HDRI mapping node"""     

    bl_idname = "hdrisa.add_rotation_driver"     
    bl_label = "Add a a driver to the active object z-rotation, based on HDRI rotation using mapping node."         
    bl_options = {'REGISTER'}

    def execute(context):
        scene = context.scene
        object = bpy.data.objects['HDRI Sun']
        
        mapping_node = None
        world_nodes = scene.world.node_tree.nodes # All nodes for the World
        
        for node in world_nodes:
            # Find the Vector Mapping node
            if isinstance(node, bpy.types.ShaderNodeMapping):
                mapping_node = node.name
                break
        
        if mapping_node:
            # Check for mapping node attributes in Blender 2.80
            if hasattr(world_nodes[mapping_node], 'rotation'):
                # Path to HDRI mapping node z-rotation value
                data_path = f'node_tree.nodes["{mapping_node}"].rotation[2]'            
            
            # If not, assume Blender 2.81 mapping node attributes
            else:
                # Path to HDRI mapping node z-rotation value
                data_path = f'node_tree.nodes["{mapping_node}"].inputs["Rotation"].default_value[2]'       
                                  
            # Driver for z rotation  
            z_rotation_driver = object.driver_add('rotation_euler', 2)

            hdri_z = z_rotation_driver.driver.variables.new() # HDRI mapping node
            obj_z = z_rotation_driver.driver.variables.new() # Object original rotation 
            
            hdri_z.name = "hdri_z"
            hdri_z.targets[0].id_type = 'WORLD'
            hdri_z.targets[0].id = scene.world
            hdri_z.targets[0].data_path = data_path

            obj_z.name = "obj_z"
            obj_z.targets[0].id_type = 'SCENE'
            obj_z.targets[0].id = scene
            obj_z.targets[0].data_path = 'hdri_sa_props.z_org'

            z_rotation_driver.driver.expression = obj_z.name + '-' + hdri_z.name

        else:
            msg = "No Mapping node defined for HDRI rotation."
            bpy.ops.message.messagebox('INVOKE_DEFAULT', message=msg)
            return {'CANCELLED'}


        return {'FINISHED'}

    execute(context)





def calculate_sun_position(context):
    """Calculate the brightest spot in the HDRI image used for the environment"""

    bl_idname = "hdrisa.calculate_sun_position"     
    bl_label = "Calculate sun position."         
    bl_options = {'REGISTER', 'UNDO'}

    def create_circular_mask(h, w, thickness, center=None, radius=None):
        """Create a circular mask used for drawing on the HDRI preview."""

        if center is None: # use the middle of the image
            center = [int(w/2), int(h/2)]
        if radius is None: # use the smallest distance between the center and image walls
            radius = min(center[0], center[1], w-center[0], h-center[1])

        Y, X = np.ogrid[:h, :w]
        dist_from_center = np.sqrt((X - center[0])**2 + (Y-center[1])**2)
        
        mask = np.logical_and(dist_from_center <= radius, dist_from_center >= (radius - thickness))
        
        return mask

    def gaussian_blur(gray_image, sigma):
        """ Apply gaussion blur to a grayscale image.
        
        Input: 
        - 2D Numpy array
        - sigma (gaussian blur radius)
        Return:
        - 2D Numpy array (blurred image)
        See https://scipython.com/book/chapter-6-numpy/examples/blurring-an-image-with-a-two-dimensional-fft/        
        """

        rows, cols = gray_image.shape
              
        # Take the 2-dimensional DFT and centre the frequencies
        ftimage = np.fft.fft2(gray_image)
        ftimage = np.fft.fftshift(ftimage)
        
        # Build and apply a Gaussian filter.
        sigmax = sigma
        sigmay = sigma
        cy, cx = rows/2, cols/2
        y = np.linspace(0, rows, rows)
        x = np.linspace(0, cols, cols)
        X, Y = np.meshgrid(x, y)
        gmask = np.exp(-(((X-cx)/sigmax)**2 + ((Y-cy)/sigmay)**2))

        ftimagep = ftimage * gmask

        # Take the inverse transform
        imagep = np.fft.ifft2(ftimagep)
        imagep = np.abs(imagep)

        return imagep

    def process_hdri(image):
        """
        Calculate the brightest point in the equirectangular HDRI image (i.e. the sun or brightest light).
        A gaussian blur is applied to the image to prevent errors from single bright pixels.
        Update the "hdri_preview" image and return the longitude and latitude in degrees.
        """

        # Get a flat Numpy array with the image pixels
        hdri_img = np.array(image.pixels[:])

        width, height = image.size
        depth = 4 # RGBA
              
        # Reshape to RGBA matrix
        hdri_img = np.array(hdri_img).reshape([height, width, depth]) 

        # Get image dimensions
        height, width = hdri_img.shape[:2]
        
        # Convert to grayscale
        gray_img = np.dot(hdri_img[...,:3], [0.299, 0.587, 0.114])
        
        # Apply gaussian blur
        gray_img = gaussian_blur(gray_img, sigma=100)

        # Find index of maximum value from 2D numpy array
        result = np.where(gray_img == np.amax(gray_img))
 
        # zip the 2 arrays to get the exact coordinates
        list_of_coordinates = list(zip(result[0], result[1]))

        # Assume only one maximum, use the first found
        max_loc_new = list_of_coordinates[0]
        
        # Get x and y coordinates for the brightest pixel 
        max_x = max_loc_new[1]
        max_y = max_loc_new[0]
        
        # Create masks to indicate sun position
        circle_mask = create_circular_mask(height, width, thickness=4, center=[max_x, max_y], radius=50)
        point_mask = create_circular_mask(height, width, thickness=4, center=[max_x, max_y], radius=5)
        
        # Draw circle
        hdri_img[:, :, 0][circle_mask] = 1 # Red
        hdri_img[:, :, 1][circle_mask] = 0 # Green 
        hdri_img[:, :, 2][circle_mask] = 0 # Blue

        # Draw center dot
        hdri_img[:, :, 0][point_mask] = 1
        hdri_img[:, :, 1][point_mask] = 0
        hdri_img[:, :, 2][point_mask] = 0

        # Find the point in longitude and latitude (degrees)
        long_deg = ((max_x * 360) / width) - 180
        lat_deg = -(((max_y * -180) / height) + 90)
                     
        # Flatten array and update the blender image object       
        image.pixels = hdri_img.ravel()
        
        return long_deg, lat_deg

    def invoke(context):
        scene = context.scene
        screen = context.screen
        world_nodes = scene.world.node_tree.nodes # All nodes for the World
        image = None
        
        # Cleanup to prevent duplicate images
        for img in bpy.data.images:
                name = img.name
                if name.startswith("hdri_sa_preview"):
                    bpy.data.images.remove(img)

        # Check if an environmental image is defined        
        for node in world_nodes:
            # Find the Environment Texture node
            if isinstance(node, bpy.types.ShaderNodeTexEnvironment): 
                image = node.image
            
        if image:
            # Make a copy of the original HDRI
            hdri_preview = image.copy()
            
            hdri_preview.name = "hdri_sa_preview." + image.file_format
            
            # Get image dimensions
            org_width = hdri_preview.size[0]
            org_height = hdri_preview.size[1]
            
            # Scale image if it's larger than 1k for improving performance
            if org_width > 1024:
                new_width = 1024
                new_height = int(org_height * (new_width / org_width))
                hdri_preview.scale(new_width, new_height)
        else:
            msg = "Please add an Environment Texture for the world."
            bpy.ops.message.messagebox('INVOKE_DEFAULT', message=msg)
            return {'CANCELLED'}

        # Calculate longitude, latitude and update HDRI preview image
        long_deg, lat_deg = process_hdri(hdri_preview)
        
        # Update properties
        scene.hdri_sa_props.long_deg = long_deg
        scene.hdri_sa_props.lat_deg = lat_deg
        scene.hdri_sa_props.sun_position_calculated = True
 
        return {'FINISHED'}

    invoke(context)

    
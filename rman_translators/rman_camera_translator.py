from .rman_translator import RmanTranslator
from ..rman_sg_nodes.rman_sg_camera import RmanSgCamera
from ..rman_sg_nodes.rman_sg_node import RmanSgNode
from ..rfb_utils import transform_utils
from ..rfb_utils import property_utils
from ..rfb_utils import object_utils
from ..rfb_utils import scene_utils
from ..rfb_utils import shadergraph_utils
from ..rfb_utils import camera_utils
from mathutils import Matrix, Vector
import math

# copied from Blender's source code
DEFAULT_SENSOR_WIDTH = 32.0
DEFAULT_SENSOR_HEIGHT = 18.0


class RmanCameraTranslator(RmanTranslator):

    def __init__(self, rman_scene):
        super().__init__(rman_scene)
        self.bl_type = 'CAMERA'
        self.s_rightHanded = self.rman_scene.rman.Types.RtMatrix4x4(1.0,0.0,0.0,0.0,
                                                               0.0,1.0,0.0,0.0,
                                                               0.0,0.0,-1.0,0.0,
                                                               0.0,0.0,0.0,1.0) 

    def _set_orientation(self, rman_sg_camera):
        camtransform = self.rman_scene.rman.Types.RtMatrix4x4()
        camtransform.Identity()
        rman_sg_camera.sg_camera_node.SetOrientTransform(self.s_rightHanded)        

    def update_transform_num_samples(self, rman_sg_camera, motion_steps ):
        rman_sg_camera.sg_node.SetTransformNumSamples(len(motion_steps))

    def _update_viewport_transform(self, rman_sg_camera):
        region_data = self.rman_scene.context.region_data
        if not region_data:
            return
        mtx = region_data.view_matrix.inverted()
        v = transform_utils.convert_matrix(mtx)
        if rman_sg_camera.cam_matrix == v:
            return 
        rman_sg_camera.cam_matrix = v
        rman_sg_camera.sg_node.SetTransform( v )    

    def _update_render_cam_transform(self, ob, rman_sg_camera, index=0, seg=0.0):

        cam = ob.data
        mtx = ob.matrix_world

        v = transform_utils.convert_matrix(mtx)
        if rman_sg_camera.cam_matrix == v:
            return

        rman_sg_camera.cam_matrix = v
        if rman_sg_camera.is_transforming:
            rman_sg_camera.sg_node.SetTransformSample(index, v, seg )              
        else:
            rman_sg_camera.sg_node.SetTransform( v )    
               

    def update_transform(self, ob, rman_sg_camera, index=0, seg=0):
        if self.rman_scene.is_viewport_render:
            self._update_viewport_transform(rman_sg_camera)
        elif self.rman_scene.is_interactive and not ob:
            self._update_viewport_transform(rman_sg_camera)
        else:
            self._update_render_cam_transform(ob, rman_sg_camera, index, seg)

    def _export_viewport_cam(self, db_name=""):  
        sg_group = self.rman_scene.sg_scene.CreateGroup(db_name) 
        rman_sg_camera = RmanSgCamera(self.rman_scene, sg_group, db_name)
        rman_sg_camera.sg_camera_node = self.rman_scene.sg_scene.CreateCamera('%s-CAMERA' % db_name)  
        sg_group.AddChild(rman_sg_camera.sg_camera_node)      
        ob = self.update_viewport_resolution(rman_sg_camera)
        self.update_viewport_cam(ob, rman_sg_camera)
        self._set_orientation(rman_sg_camera)
        self._update_viewport_transform(rman_sg_camera)  
        return rman_sg_camera        

    def _export_render_cam(self, ob, db_name=""):
        sg_group = self.rman_scene.sg_scene.CreateGroup(db_name) 
        rman_sg_camera = RmanSgCamera(self.rman_scene, sg_group, db_name)
        rman_sg_camera.sg_camera_node = self.rman_scene.sg_scene.CreateCamera('%s-CAMERA' % db_name) 
        sg_group.AddChild(rman_sg_camera.sg_camera_node)             
        if self.rman_scene.do_motion_blur:
            rman_sg_camera.is_transforming = object_utils.is_transforming(ob)
            mb_segs = self.rman_scene.bl_scene.renderman.motion_segments
            if ob.renderman.motion_segments_override:
                mb_segs = ob.renderman.motion_segments
            if mb_segs > 1:
                subframes = scene_utils._get_subframes_(mb_segs, self.rman_scene.bl_scene)
                rman_sg_camera.motion_steps = subframes  
                self.update_transform_num_samples(rman_sg_camera, subframes )                
            else:
                rman_sg_camera.is_transforming = False
        self._update_render_cam(ob, rman_sg_camera)
        self._set_orientation(rman_sg_camera)
        self._update_render_cam_transform(ob, rman_sg_camera)
        return rman_sg_camera                  

    def export(self, ob, db_name=""):
        if self.rman_scene.is_viewport_render:
            return self._export_viewport_cam(db_name)
        elif self.rman_scene.is_interactive and not ob:
            return self._export_viewport_cam(db_name)
        else:
            return self._export_render_cam(ob, db_name)

    def update(self, ob, rman_sg_camera):
        if self.rman_scene.is_viewport_render:
            return self.update_viewport_cam(rman_sg_camera)
        else:
            return self._update_render_cam(ob, rman_sg_camera)   

    def update_viewport_resolution(self, rman_sg_camera):
        region = self.rman_scene.context.region
        region_data = self.rman_scene.context.region_data

        # get the current resolution multiplier
        res_mult = self.rman_scene.viewport_render_res_mult

        width = int(region.width * res_mult)
        height = int(region.height * res_mult)      

        updated = False
        resolution_updated = False
        ob = None
        prop = rman_sg_camera.sg_camera_node.GetProperties()
        crop_window = [0.0, 1.0, 0.0, 1.0]
        if rman_sg_camera.res_width != width:
            rman_sg_camera.res_width = width
            updated = True
            resolution_updated = True
        
        if rman_sg_camera.res_height != height:
            rman_sg_camera.res_height = height                
            updated = True      
            resolution_updated = True

        if region_data:
            if rman_sg_camera.view_perspective != region_data.view_perspective:
                rman_sg_camera.view_perspective = region_data.view_perspective
                updated = True            

            if rman_sg_camera.view_camera_zoom != self.rman_scene.context.region_data.view_camera_zoom:
                rman_sg_camera.view_camera_zoom = self.rman_scene.context.region_data.view_camera_zoom
                updated = True

            if rman_sg_camera.view_camera_offset != self.rman_scene.context.region_data.view_camera_offset:
                rman_sg_camera.view_camera_offset = self.rman_scene.context.region_data.view_camera_offset
                updated = True            

            if region_data.view_perspective == 'CAMERA':
                ob = self.rman_scene.bl_scene.camera    
                if self.rman_scene.context.space_data.use_local_camera:
                    ob = self.rman_scene.context.space_data.camera      

                cam = ob.data
                r = self.rman_scene.bl_scene.render

                xaspect, yaspect, aspectratio = camera_utils.render_get_aspect_(r, cam, x=width, y=height)

                # magic zoom formula copied from blenderseed, which got it from cycles
                zoom = 4 / ((math.sqrt(2) + rman_sg_camera.view_camera_zoom / 50) ** 2)   

                if cam.type == 'ORTHO':
                    lens = cam.ortho_scale
                    xaspect = xaspect * lens / (aspectratio * 2.0)
                    yaspect = yaspect * lens / (aspectratio * 2.0)    
                    aspectratio = lens / 2.0   
                else:
                    lens = ob.data.lens             
                    
                # shift and offset            
                offset = tuple(rman_sg_camera.view_camera_offset)
                dx = 2.0 * (aspectratio * cam.shift_x + offset[0] * xaspect * 2.0)
                dy = 2.0 * (aspectratio * cam.shift_y + offset[1] * yaspect * 2.0)       
                
                if rman_sg_camera.lens != lens:
                    rman_sg_camera.lens = lens
                    updated = True

                if rman_sg_camera.shift_x != cam.shift_x:
                    rman_sg_camera.shift_x = cam.shift_x
                    updated = True

                if rman_sg_camera.shift_y != cam.shift_y:
                    rman_sg_camera.shift_y = cam.shift_y
                    updated = True                    

                if rman_sg_camera.xaspect != xaspect or rman_sg_camera.yaspect != yaspect: 
                    rman_sg_camera.xaspect = xaspect
                    rman_sg_camera.yaspect = yaspect  
                    rman_sg_camera.aspectratio = aspectratio
                    updated = True                    

                sw = [-xaspect * zoom, xaspect * zoom, -yaspect * zoom, yaspect * zoom]
                sw[0] += dx
                sw[1] += dx
                sw[2] += dy
                sw[3] += dy
 
                if rman_sg_camera.screenwindow != sw:
                    rman_sg_camera.screenwindow = sw
                    updated = True
                
                prop.SetFloatArray(self.rman_scene.rman.Tokens.Rix.k_Ri_ScreenWindow, sw, 4)  

                if r.use_border:

                    x0, x1, y0, y1 = camera_utils.get_viewport_cam_borders(ob, r, region, region_data, self.rman_scene.bl_scene)
                    min_x = (x0) / width
                    max_x = (x1) / width
                    min_y = 1.0 - (y0 / height)
                    max_y = 1.0 - (y1 / height)

                    crop_window = [min_x, max_x, min_y, max_y]


            elif region_data.view_perspective ==  'PERSP': 
                if self.rman_scene.context.space_data.use_render_border:
                    space = self.rman_scene.context.space_data
                    min_x = space.render_border_min_x
                    max_x = space.render_border_max_x
                    if (min_x >= max_x):
                        min_x = 0.0
                        max_x = 1.0
                    min_y = 1.0 - space.render_border_min_y
                    max_y = 1.0 - space.render_border_max_y
                    crop_window = [min_x, max_x, min_y, max_y]

                ob = self.rman_scene.context.space_data.camera 
                cam = None
                if ob:
                    cam = ob.data
                r = self.rman_scene.bl_scene.render

                xaspect, yaspect, aspectratio = camera_utils.render_get_aspect_(r, cam, x=width, y=height)          
                zoom = 2.0
                if not cam:
                    zoom = 1.0

                # shift and offset            
                shift_x = 0.0
                shift_y = 0.0
                if cam:
                    shift_x = cam.shift_x
                    shift_y = cam.shift_y

                # FIXME? It seems like we don't need the view_camera_offset for some reason
                # Need to do some more testing, but taking it into account seems to shift the image
                offset = (0.0, 0.0) #tuple(rman_sg_camera.view_camera_offset)
                dx = 2.0 * (aspectratio * shift_x + offset[0] * xaspect * 2.0)
                dy = 2.0 * (aspectratio * shift_y + offset[1] * yaspect * 2.0)               

                if rman_sg_camera.lens != self.rman_scene.context.space_data.lens:
                    rman_sg_camera.lens = self.rman_scene.context.space_data.lens
                    updated = True
                    
                if rman_sg_camera.xaspect != xaspect or rman_sg_camera.yaspect != yaspect:
                    rman_sg_camera.xaspect = xaspect
                    rman_sg_camera.yaspect = yaspect  
                    rman_sg_camera.aspectratio = aspectratio
                    updated = True               

                if rman_sg_camera.shift_x != shift_x:
                    rman_sg_camera.shift_x = shift_x
                    updated = True

                if rman_sg_camera.shift_y != shift_y:
                    rman_sg_camera.shift_y = shift_y
                    updated = True                        

                sw = [-xaspect * zoom, xaspect * zoom, -yaspect * zoom, yaspect * zoom]
                sw[0] += dx
                sw[1] += dx
                sw[2] += dy
                sw[3] += dy
 
                if rman_sg_camera.screenwindow != sw:
                    rman_sg_camera.screenwindow = sw
                    updated = True
                
                prop.SetFloatArray(self.rman_scene.rman.Tokens.Rix.k_Ri_ScreenWindow, sw, 4)                                     

            else: 
                ob = self.rman_scene.context.space_data.camera 
                cam = None
                if ob:
                    cam = ob.data
                
                r = self.rman_scene.bl_scene.render

                xaspect, yaspect, aspectratio = camera_utils.render_get_aspect_(r, cam, x=width, y=height)

                # 2.0 zoom value copied from cycles
                zoom = 2.0
                lens = self.rman_scene.context.space_data.lens
                if cam:
                    sensor = cam.sensor_height \
                        if cam.sensor_fit == 'VERTICAL' else cam.sensor_width
                else:
                    sensor = DEFAULT_SENSOR_WIDTH

                ortho_scale = region_data.view_distance * sensor / lens
                xaspect = xaspect * ortho_scale / (aspectratio * 2.0)
                yaspect = yaspect * ortho_scale / (aspectratio * 2.0)
                aspectratio = ortho_scale / 2.0  

                if rman_sg_camera.xaspect != xaspect or rman_sg_camera.yaspect != yaspect:
                    rman_sg_camera.xaspect = xaspect
                    rman_sg_camera.yaspect = yaspect  
                    rman_sg_camera.aspectratio = aspectratio
                    updated = True                               

                # shift and offset   
                shift_x = 0.0
                shift_y = 0.0
                if cam:
                    shift_x = cam.shift_x
                    shift_y = cam.shift_y       

                # FIXME? See comment above                      
                offset = (0.0, 0.0) #tuple(rman_sg_camera.view_camera_offset)
                dx = 2.0 * (aspectratio * shift_x + offset[0] * xaspect * 2.0)
                dy = 2.0 * (aspectratio * shift_y + offset[1] * yaspect * 2.0)                            

                sw = [-xaspect * zoom, xaspect * zoom, -yaspect * zoom, yaspect * zoom]
                sw[0] += dx
                sw[1] += dx
                sw[2] += dy
                sw[3] += dy

                prop.SetFloatArray(self.rman_scene.rman.Tokens.Rix.k_Ri_ScreenWindow, sw, 4)                                                                               

        if updated:
            options = self.rman_scene.sg_scene.GetOptions()
            options.SetFloat(self.rman_scene.rman.Tokens.Rix.k_Ri_FormatPixelAspectRatio, 1.0)   
            options.SetIntegerArray(self.rman_scene.rman.Tokens.Rix.k_Ri_FormatResolution, (width, height), 2)
            if resolution_updated:

                # This is super yucky. We need to be able to tell the 
                # crop handler to stop drawing and reset the 
                # crop window when the resolution changes. Unfortunately
                # Blender doesn't seem to allow us to call operators during this
                # state, so we tell the handler to reset directly. 
                from ..rman_ui.rman_ui_viewport import __DRAW_CROP_HANDLER__ as crop_handler
                if crop_handler and crop_handler.crop_windowing:
                    crop_handler.reset()
                    crop_window = [0.0, 1.0, 0.0, 1.0]
                    
            options.SetFloatArray(self.rman_scene.rman.Tokens.Rix.k_Ri_CropWindow, crop_window, 4)
            self.rman_scene.sg_scene.SetOptions(options)
            rman_sg_camera.sg_camera_node.SetProperties(prop)
            return ob
        return None

    def update_viewport_cam(self, ob, rman_sg_camera, force_update=False):
        region = self.rman_scene.context.region
        region_data = self.rman_scene.context.region_data

        # get the current resolution multiplier
        res_mult = self.rman_scene.viewport_render_res_mult

        width = rman_sg_camera.res_width
        height = rman_sg_camera.res_height
        view_camera_zoom = rman_sg_camera.view_camera_zoom

        rman_sg_camera.projection_shader = None
        fov = -1

        updated = False

        if rman_sg_camera.view_perspective == 'CAMERA':
            ob = ob.original
            cam = ob.data
            rman_sg_camera.bl_camera = ob
            cam_rm = cam.renderman

            aspectratio = rman_sg_camera.aspectratio
            lens = cam.lens
            sensor = cam.sensor_height \
                if cam.sensor_fit == 'VERTICAL' else cam.sensor_width

            if cam.type == 'ORTHO':
                rman_sg_camera.projection_shader = self.rman_scene.rman.SGManager.RixSGShader("Projection", "PxrOrthographic", "proj")   
                updated = True
            else:
                fov = 360.0 * math.atan((sensor * 0.5) / lens / aspectratio) / math.pi

                if rman_sg_camera.rman_fov == -1:
                    rman_sg_camera.rman_fov = fov  
                    updated = True
                elif rman_sg_camera.rman_fov != fov:              
                    rman_sg_camera.rman_fov = fov  
                    updated = True

                node = shadergraph_utils.find_projection_node(ob)        
                if node:
                    rman_sg_camera.projection_shader = self.rman_scene.rman.SGManager.RixSGShader("Projection", node.bl_label, "proj")
                    rman_sg_node = RmanSgNode(self.rman_scene, rman_sg_camera.projection_shader, "")                           
                    property_utils.property_group_to_rixparams(node, rman_sg_node, rman_sg_camera.projection_shader, ob=cam) 
                    projparams = rman_sg_camera.projection_shader.params
                    if cam_rm.rman_use_cam_fov:
                        projparams.SetFloat(self.rman_scene.rman.Tokens.Rix.k_fov, fov) 
  
                else:                
                    rman_sg_camera.projection_shader = self.rman_scene.rman.SGManager.RixSGShader("Projection", "PxrCamera", "proj")
                    projparams = rman_sg_camera.projection_shader.params         
                    projparams.SetFloat(self.rman_scene.rman.Tokens.Rix.k_fov, fov) 

                if cam_rm.rman_use_dof:
                    if cam_rm.rman_focus_object:
                        dof_focal_distance = (ob.location - cam_rm.rman_focus_object.location).length
                    else:
                        dof_focal_distance = cam_rm.rman_focus_distance
                    if dof_focal_distance > 0.0:
                        dof_focal_length = (cam.lens * 0.001)
                        projparams.SetFloat(self.rman_scene.rman.Tokens.Rix.k_fStop, cam_rm.rman_aperture_fstop)
                        projparams.SetFloat(self.rman_scene.rman.Tokens.Rix.k_focalLength, dof_focal_length)
                    projparams.SetFloat(self.rman_scene.rman.Tokens.Rix.k_focalDistance, dof_focal_distance)                       

        elif rman_sg_camera.view_perspective ==  'PERSP': 
            cam = None
            if ob:
                cam = ob.data
            rman_sg_camera.bl_camera = ob
            
            aspectratio = rman_sg_camera.aspectratio
            lens = rman_sg_camera.lens 
            if cam:
                sensor = cam.sensor_height \
                    if cam.sensor_fit == 'VERTICAL' else cam.sensor_width
                     
                fov = 360.0 * math.atan((sensor * 0.5) / lens / aspectratio) / math.pi
            else:
                # code from: 
                # https://blender.stackexchange.com/questions/46391/how-to-convert-spaceview3d-lens-to-field-of-view
                region_data = self.rman_scene.context.region_data
                vmat_inv = region_data.view_matrix.inverted()
                pmat = region_data.perspective_matrix @ vmat_inv
                fov = 360.0 * math.atan(1.0/pmat[1][1]) / math.pi

            if rman_sg_camera.rman_fov == -1:
                rman_sg_camera.rman_fov = fov  
                updated = True
            elif rman_sg_camera.rman_fov != fov:              
                rman_sg_camera.rman_fov = fov  
                updated = True               

            rman_sg_camera.projection_shader = self.rman_scene.rman.SGManager.RixSGShader("Projection", "PxrCamera", "proj")
            projparams = rman_sg_camera.projection_shader.params         
            projparams.SetFloat(self.rman_scene.rman.Tokens.Rix.k_fov, fov)   

        else:
            # orthographic
            rman_sg_camera.projection_shader = self.rman_scene.rman.SGManager.RixSGShader("Projection", "PxrOrthographic", "proj")  
            updated = True        

        if updated or force_update:   
            rman_sg_camera.sg_camera_node.SetProjection(rman_sg_camera.projection_shader)         

    def _set_fov(self, ob, cam, aspectratio, projparams):
        lens = cam.lens
        cam_rm = cam.renderman
        sensor = cam.sensor_height \
            if cam.sensor_fit == 'VERTICAL' else cam.sensor_width

        fov = 360.0 * math.atan((sensor * 0.5) / lens / aspectratio) / math.pi            
        
        dx = 2.0 * (aspectratio * cam.shift_x) 
        dy = 2.0 * (aspectratio * cam.shift_y)   
        projparams.SetFloat(self.rman_scene.rman.Tokens.Rix.k_fov, fov)

        if cam_rm.rman_use_dof:
            if cam_rm.rman_focus_object:
                dof_focal_distance = (ob.location - cam_rm.rman_focus_object.location).length
            else:
                dof_focal_distance = cam_rm.rman_focus_distance
            if dof_focal_distance > 0.0:
                dof_focal_length = (cam.lens * 0.001)
                projparams.SetFloat(self.rman_scene.rman.Tokens.Rix.k_fStop, cam_rm.rman_aperture_fstop)
                projparams.SetFloat(self.rman_scene.rman.Tokens.Rix.k_focalLength, dof_focal_length)
            projparams.SetFloat(self.rman_scene.rman.Tokens.Rix.k_focalDistance, dof_focal_distance)          

    def _update_render_resolution(self, ob, rman_sg_camera):
        r = self.rman_scene.bl_scene.render
        cam = ob.data
        rm = self.rman_scene.bl_scene.renderman
        cam_rm = cam.renderman
        rman_sg_camera.bl_camera = ob

        xaspect, yaspect, aspectratio = camera_utils.render_get_aspect_(r, cam)

        options = self.rman_scene.sg_scene.GetOptions()

        if self.rman_scene.bl_scene.render.use_border and not self.rman_scene.bl_scene.render.use_crop_to_border:
            min_x = self.rman_scene.bl_scene.render.border_min_x
            max_x = self.rman_scene.bl_scene.render.border_max_x
            if (min_x >= max_x):
                min_x = 0.0
                max_x = 1.0
            min_y = 1.0 - self.rman_scene.bl_scene.render.border_min_y
            max_y = 1.0 - self.rman_scene.bl_scene.render.border_max_y
            if (min_y >= max_y):
                min_y = 0.0
                max_y = 1.0

            options.SetFloatArray(self.rman_scene.rman.Tokens.Rix.k_Ri_CropWindow, (min_x, max_x, min_y, max_y), 4)   

        # convert the crop border to screen window, flip y
        resolution = camera_utils.render_get_resolution_(self.rman_scene.bl_scene.render)
        if self.rman_scene.bl_scene.render.use_border and self.rman_scene.bl_scene.render.use_crop_to_border:
            res_x = resolution[0] * (self.rman_scene.bl_scene.render.border_max_x -
                                    self.rman_scene.bl_scene.render.border_min_x)
            res_y = resolution[1] * (self.rman_scene.bl_scene.render.border_max_y -
                                    self.rman_scene.bl_scene.render.border_min_y)

            options.SetIntegerArray(self.rman_scene.rman.Tokens.Rix.k_Ri_FormatResolution, (int(res_x), int(res_y)), 2)
            options.SetFloat(self.rman_scene.rman.Tokens.Rix.k_Ri_FormatPixelAspectRatio, 1.0)        
        else:            
            options.SetIntegerArray(self.rman_scene.rman.Tokens.Rix.k_Ri_FormatResolution, (resolution[0], resolution[1]), 2)
            options.SetFloat(self.rman_scene.rman.Tokens.Rix.k_Ri_FormatPixelAspectRatio, 1.0)

        self.rman_scene.sg_scene.SetOptions(options)  

        # update screen window
        self._update_screen_window(ob, xaspect, yaspect, aspectratio)    

    def _update_screen_window(self, ob, xaspect, yaspect, aspectratio):
        cam = ob.data

        options = self.rman_scene.sg_scene.GetOptions()
        dx = 0
        dy = 0

        if self.rman_scene.bl_scene.render.use_border and self.rman_scene.bl_scene.render.use_crop_to_border:
            screen_min_x = -xaspect + 2.0 * self.rman_scene.bl_scene.render.border_min_x * xaspect
            screen_max_x = -xaspect + 2.0 * self.rman_scene.bl_scene.render.border_max_x * xaspect
            screen_min_y = -yaspect + 2.0 * (self.rman_scene.bl_scene.render.border_min_y) * yaspect
            screen_max_y = -yaspect + 2.0 * (self.rman_scene.bl_scene.render.border_max_y) * yaspect

            options.SetFloatArray(self.rman_scene.rman.Tokens.Rix.k_Ri_ScreenWindow, (screen_min_x, screen_max_x, screen_min_y, screen_max_y), 4)   
        else:            
            if cam.type == 'PANO':
                options.SetFloatArray(self.rman_scene.rman.Tokens.Rix.k_Ri_ScreenWindow, (-1, 1, -1, 1), 4)
            elif cam.type == 'ORTHO':
                lens = cam.ortho_scale
                xaspect = xaspect * lens / (aspectratio * 2.0)
                yaspect = yaspect * lens / (aspectratio * 2.0)    
                aspectratio = lens / 2.0   
                dx = 2.0 * (aspectratio * cam.shift_x) 
                dy = 2.0 * (aspectratio * cam.shift_y)   
                sw = [-xaspect, xaspect, -yaspect, yaspect]
                sw[0] += dx
                sw[1] += dx
                sw[2] += dy
                sw[3] += dy                
                options.SetFloatArray(self.rman_scene.rman.Tokens.Rix.k_Ri_ScreenWindow, sw, 4)   
            else:
                options.SetFloatArray(self.rman_scene.rman.Tokens.Rix.k_Ri_ScreenWindow, (-xaspect+dx, xaspect+dx, -yaspect+dy, yaspect+dy), 4)        

        self.rman_scene.sg_scene.SetOptions(options)  

    def _update_render_cam(self, ob, rman_sg_camera):

        r = self.rman_scene.bl_scene.render
        cam = ob.data
        rm = self.rman_scene.bl_scene.renderman
        cam_rm = cam.renderman
        rman_sg_camera.bl_camera = ob

        xaspect, yaspect, aspectratio = camera_utils.render_get_aspect_(r, cam)
        rman_sg_camera.projection_shader = None

        node = shadergraph_utils.find_projection_node(ob)        
        if node:
            rman_sg_camera.projection_shader = self.rman_scene.rman.SGManager.RixSGShader("Projection", node.bl_label, "proj")
            rman_sg_node = RmanSgNode(self.rman_scene, rman_sg_camera.projection_shader, "")                           
            property_utils.property_group_to_rixparams(node, rman_sg_node, rman_sg_camera.projection_shader, ob=cam)   
            if cam_rm.rman_use_cam_fov:
                self._set_fov(ob, cam, aspectratio, rman_sg_camera.projection_shader.params)


        elif cam.type == 'PERSP':
            rman_sg_camera.projection_shader = self.rman_scene.rman.SGManager.RixSGShader("Projection", "PxrCamera", "proj")
            self._set_fov(ob, cam, aspectratio, rman_sg_camera.projection_shader.params)              
                     
        elif cam.type == 'PANO':
            rman_sg_camera.projection_shader = self.rman_scene.rman.SGManager.RixSGShader("Projection", "PxrSphereCamera", "proj")
            projparams = rman_sg_camera.projection_shader.params
            projparams.SetFloat("hsweep", 360)
            projparams.SetFloat("vsweep", 180)           
        else:
            lens = cam.ortho_scale
            xaspect = xaspect * lens / (aspectratio * 2.0)
            yaspect = yaspect * lens / (aspectratio * 2.0)
            rman_sg_camera.projection_shader = self.rman_scene.rman.SGManager.RixSGShader("Projection", "PxrOrthographic", "proj")

        # Update screen window. Ortho scale may have change
        self._update_screen_window(ob, xaspect, yaspect, aspectratio)

        rman_sg_camera.sg_camera_node.SetProjection(rman_sg_camera.projection_shader)
        prop = rman_sg_camera.sg_camera_node.GetProperties()

        # Shutter Timings
        prop.SetFloat(self.rman_scene.rman.Tokens.Rix.k_shutterOpenTime, self.rman_scene.bl_scene.renderman.shutter_open)
        prop.SetFloat(self.rman_scene.rman.Tokens.Rix.k_shutterCloseTime, self.rman_scene.bl_scene.renderman.shutter_close)

        # Shutter Opening
        if cam_rm.rman_use_shutteropening:
            shutteropenings = [
                cam_rm.rman_shutteropening_c1,
                cam_rm.rman_shutteropening_c2,
                cam_rm.rman_shutteropening_d1,
                cam_rm.rman_shutteropening_d2,
                cam_rm.rman_shutteropening_e1,
                cam_rm.rman_shutteropening_e2,
                cam_rm.rman_shutteropening_f1,
                cam_rm.rman_shutteropening_f2
            ]
            prop.SetFloatArray(self.rman_scene.rman.Tokens.Rix.k_shutteropening, shutteropenings, 8)

        # Stereo Planes
        rman_stereoplanedepths_arraylen = getattr(cam_rm, 'rman_stereoplanedepths_arraylen', 0)
        rman_stereoplaneoffsets_arraylen = getattr(cam_rm, 'rman_stereoplaneoffsets_arraylen', 0)
        if (rman_stereoplanedepths_arraylen > 0) and (rman_stereoplaneoffsets_arraylen > 0) and (rman_stereoplanedepths_arraylen == rman_stereoplaneoffsets_arraylen):
            stereoplanedepths = []
            for i in range(rman_stereoplanedepths_arraylen):
                val = getattr(cam_rm, 'rman_stereoplanedepths[%d]' % i)
                stereoplanedepths.append(val)

            prop.SetFloatArray(self.rman_scene.rman.Tokens.Rix.k_stereoplanedepths, stereoplanedepths, rman_stereoplanedepths_arraylen)

            stereoplaneoffsets = []
            for i in range(rman_stereoplaneoffsets_arraylen):
                val = getattr(cam_rm, 'rman_stereoplaneoffsets[%d]' % i)
                stereoplaneoffsets.append(val)

            prop.SetFloatArray(self.rman_scene.rman.Tokens.Rix.k_stereoplaneoffsets, stereoplaneoffsets, rman_stereoplaneoffsets_arraylen)            

        # clipping planes         
        prop.SetFloat(self.rman_scene.rman.Tokens.Rix.k_nearClip, cam.clip_start)
        prop.SetFloat(self.rman_scene.rman.Tokens.Rix.k_farClip, cam.clip_end)

        # aperture
        prop.SetInteger(self.rman_scene.rman.Tokens.Rix.k_apertureNSides, cam_rm.rman_aperture_blades)
        prop.SetFloat(self.rman_scene.rman.Tokens.Rix.k_apertureAngle, cam_rm.rman_aperture_rotation)
        prop.SetFloat(self.rman_scene.rman.Tokens.Rix.k_apertureRoundness, cam_rm.rman_aperture_roundness)
        prop.SetFloat(self.rman_scene.rman.Tokens.Rix.k_apertureDensity, cam_rm.rman_aperture_density)

        prop.SetFloat(self.rman_scene.rman.Tokens.Rix.k_dofaspect, cam_rm.rman_aperture_ratio)    

        rman_sg_camera.sg_camera_node.SetProperties(prop)
    

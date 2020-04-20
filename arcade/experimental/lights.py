from array import array
from typing import Tuple, Sequence

from arcade.gl import Context
from arcade import Color, get_window, get_projection, get_scaling_factor, set_viewport
from arcade import gl
from arcade.experimental import geometry

class Light:
    HARD = 1.0
    SOFT = 0.0

    def __init__(self, position: Tuple[float, float],
                 radius: float = 50.0, color: Tuple[int, int, int] = (255, 255, 255),
                 mode='hard', usage: str = 'dynamic'):
        """Create a Light.

        Note: It's important to separate lights that don' change properties
        and static ones with the `usage` parameter.

        :param Tuple[float, float] position: the position of the light
        :param float radius: The radius of the light
        :param float mode: `hard` or `soft`
        :param str usage: `static` or `dynamic`.
        """
        self._center_x = position[0]
        self._center_y = position[1]
        self._radius = radius
        self._attenuation = Light.HARD if mode == 'hard' else Light.SOFT
        self._color = color
        self._light_layer = None

    @property
    def position(self) -> Tuple[float, float]:
        """Get or set the light position"""
        return self._center_x, self._center_y

    @position.setter
    def position(self, value):
        # if self._light_layer:
        self._light_layer._rebuild = True
        self._center_x, self._center_y = value

    @property
    def radius(self) -> float:
        """Get or set the light size"""
        if self._light_layer:
            self._light_layer._rebuild = True
        return self._radius

    @radius.setter
    def radius(self, value):
        self._radius = value


class LightLayer:

    def __init__(self, size: Tuple[int, int]):
        """Create a LightLayer

        The size of a layer should ideally be of the same size and the screen.

        :param Tuple[int, int] size: Width and height of light layer
        """
        self.window = get_window()
        if self.window is None:
            raise RuntimeError("Cannot find window")
        self.ctx = self.window.ctx
        self._lights = []

        self._prev_target = None
        self._rebuild = False
        self._stride = 28
        self._buffer = self.ctx.buffer(reserve=self._stride * 100)
        self._vao = self.ctx.geometry([
            gl.BufferDescription(
                self._buffer,
                '2f 1f 1f 3f',
                ['in_vert', 'in_radius', 'in_attenuation', 'in_color'],
                normalized=['in_color'],
            ),
        ])
        self._light_program = self.ctx.load_program(
            vertex_shader=":resources:shaders/lights/point_lights_vs.glsl",
            geometry_shader=":resources:shaders/lights/point_lights_geo.glsl",
            fragment_shader=":resources:shaders/lights/point_lights_fs.glsl",
        )
        self._combine_program = self.ctx.load_program(
            vertex_shader=":resources:shaders/lights/combine_vs.glsl",
            fragment_shader=":resources:shaders/lights/combine_fs.glsl",
        )
        self._quad_fs = geometry.quad_fs(size=(2.0, 2.0))
        self.resize(*size)

    def resize(self, width, height):
        pixel_scale = get_scaling_factor(self.window)
        self._size = width * pixel_scale, height * pixel_scale
        self._light_buffer = self.ctx.framebuffer(color_attachments=self.ctx.texture((width, height), components=4))
        self._diffuse_buffer = self.ctx.framebuffer(color_attachments=self.ctx.texture((width, height), components=4))        

    def add(self, light: Light):
        """Add a Light to the layer"""
        self._lights.append(light)
        light._light_layer = self
        self._rebuild = True

    def extend(self, lights: Sequence[Light]):
        for light in lights:
            self.add(light)

    def remove(self, light: Light):
        """Remove a light to the layer"""
        self._lights.remove(light)
        light._light_layer = None
        self._rebuild = True

    def __enter__(self):
        self._prev_target = self.ctx.active_framebuffer
        self._diffuse_buffer.use()
        self._diffuse_buffer.clear()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._prev_target.use()

    def draw(self, target=None, ambient_color: Color = (64, 64, 64)):
        if target is None:
            target = self.window

        self._light_program['Projection'] = get_projection().flatten()

        # Re-build light data if needed
        if self._rebuild:
            data = []
            for light in self._lights:
                data.extend(light.position)
                data.append(light.radius)
                data.append(light._attenuation)
                data.extend(light._color)

            while self._buffer.size < len(data) * self._stride:
                self._buffer.orphan(double=True)

            self._buffer.write(data=array('f', data).tobytes())
            self._rebuild = False

        # Render to light buffer
        self._light_buffer.use()
        self._light_buffer.clear()
        self.ctx.enable(self.ctx.BLEND)        
        self.ctx.blend_func = self.ctx.BLEND_ADDITIVE
        self._vao.render(self._light_program, mode=self.ctx.POINTS, vertices=len(self._lights))
        self.ctx.blend_func = self.ctx.BLEND_DEFAULT

        # Combine pass
        target.use()        
        self._combine_program['diffuse_buffer'] = 0
        self._combine_program['light_buffer'] = 1
        self._combine_program['ambient'] = ambient_color[:3]
        self._diffuse_buffer.color_attachments[0].use(0)
        self._light_buffer.color_attachments[0].use(1)

        self._quad_fs.render(self._combine_program)

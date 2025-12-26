import pygame
import pygame.freetype
import datetime
import os
import random
import math
import shutil
from PIL import Image, ImageOps

#region Constants
WINDOW_WIDTH = 1366
WINDOW_HEIGHT = 768
IMAGE_FOLDER_URL = "../w-slide/public/temp/"
DESTINATION_FOLDER = "tmp/"
WITH_RESIZE = False #set to true when adding new photos
SKIP_COPY = True #if everything's ok, set to true, otherwise move to false

FONT_SIZE_SM = 40
FONT_SIZE = 60
FONT_SIZE_XLARGE = 100
FONT_URL = "assets/segoeuil.ttf"
TEXT_COLOR = (255, 255, 255)
TEXT_PADDING = 20

SLIDE_DURATION_MS = 800
SCALE_DURATION_MS = 5000
FLIP_DURATION_MS = 1000
CROSSFADE_DURATION_MS = 1200
SCALE_FACTOR = 0.05

EXIF_KEY = 274
MOSAIC_KIND_SINGLE_IMAGE = "single_image"
MOSAIC_KIND_MULTI_IMAGE = "multi_image" # Not implemented yet

ANIMATION_TYPE_SLIDE_IN = "slide_in"
ANIMATION_TYPE_FLIP = "flip"
ANIMATION_TYPE_CROSSFADE = "crossfade"
#endregion Constants

#region Init
pygame.init()
#screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.RESIZABLE)
screen = pygame.display.set_mode((0 ,0), pygame.FULLSCREEN)
clock = pygame.time.Clock()
font_small = pygame.freetype.Font(FONT_URL, FONT_SIZE_SM)
font = pygame.freetype.Font(FONT_URL, FONT_SIZE)
font_xlarge = pygame.freetype.Font(FONT_URL, FONT_SIZE_XLARGE)
images_paths = []
current_image_idx = 0
current_display_mosaic = None
background_mosaic = None
running = True
#endregion Init

#region TextFunctions
def zero_fix(num):
    if num < 10:
        return "0" + str(num)
    return str(num)

def print_date():
    text_surface, rect = font.render(datetime.datetime.now().strftime("%A, %B %d"), TEXT_COLOR)
    screen.blit(text_surface, (TEXT_PADDING, WINDOW_HEIGHT - 100))

def print_time():
    text_surface, rect = font_xlarge.render(zero_fix(datetime.datetime.now().hour) + ":" + zero_fix(datetime.datetime.now().minute), TEXT_COLOR)
    screen.blit(text_surface, (TEXT_PADDING, WINDOW_HEIGHT - 180))
#endregion TextFunctions

#region ImageFunctions
def copy_folder(folder_url, destination_folder):
    if os.path.exists(destination_folder):
        shutil.rmtree(destination_folder)
    else:
        os.mkdir(destination_folder)
    shutil.copytree(folder_url, destination_folder)

def load_images(folder_url):
    for root, dirs, files in os.walk(folder_url):
        for file in files:
            if file.startswith("."):
                continue
            if file.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.gif')):
                images_paths.append(os.path.join(root, file))
    random.shuffle(images_paths)

def get_orientation(image_url):
    try:
        with Image.open(image_url) as img:
            exif_data = img._getexif()
            if exif_data is None:
                return 0
            elif exif_data and EXIF_KEY in exif_data:
                return exif_data[EXIF_KEY]
    except (IOError, AttributeError, KeyError):
        return 0
    return 0

def resize_all_images(folder_url, destination_folder, width, height):
    if os.path.exists(destination_folder):
        shutil.rmtree(destination_folder)
    os.mkdir(destination_folder)

    for root, dirs, files in os.walk(folder_url):
        for file in files:
            if file.startswith("."):
                continue
            if file.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.gif')):
                resize_image(root, file, destination_folder, width, height)

def resize_image(root, file, destination_folder, width, height):
    image_url = os.path.join(root, file)
    destination_image_url = os.path.join(destination_folder, file)
    try:
        with Image.open(image_url) as img:
            img = ImageOps.exif_transpose(img)
            img.thumbnail((width, height), Image.Resampling.LANCZOS)
            img.save(destination_image_url)
    except IOError:
        print("Error resizing image:", image_url)
#endregion ImageFunctions

class AnimatedMosaic:
    def __init__(self, mosaic_kind, image_urls=None, animation_type=None, previous_image_info=None):
        self.kind = mosaic_kind
        self.animation_type = animation_type if animation_type else ANIMATION_TYPE_SLIDE_IN
        self.animation_stage = "start"
        self.stage_start_time = pygame.time.get_ticks()
        
        self.current_display_surface = None
        self.rect = pygame.Rect(0, 0, 0, 0)

        self.fading_out_surface = None
        self.fading_out_rect = None

        if self.kind == MOSAIC_KIND_SINGLE_IMAGE:
            self.image_url = image_urls[0]
            self.original_image = pygame.image.load(self.image_url).convert_alpha()
            self.orientation = get_orientation(self.image_url)

            if self.orientation == 3:
                self.original_image = pygame.transform.rotate(self.original_image, 180)
            elif self.orientation == 6:
                self.original_image = pygame.transform.rotate(self.original_image, -90)
            elif self.orientation == 8:
                self.original_image = pygame.transform.rotate(self.original_image, 90)

            self.original_width = self.original_image.get_width()
            self.original_height = self.original_image.get_height()

            if self.original_width > WINDOW_WIDTH or self.original_height > WINDOW_HEIGHT:
                if self.original_width > self.original_height:
                    scale_factor_r = WINDOW_WIDTH / self.original_width
                else:
                    scale_factor_r = WINDOW_HEIGHT / self.original_height
                self.original_width = int(self.original_width * scale_factor_r)
                self.original_height = int(self.original_height * scale_factor_r)

            if previous_image_info:
                self.previous_image_url = previous_image_info[2]
                self.previous_image_surface = pygame.image.load(self.previous_image_url).convert_alpha()
                self.original_previous_width = previous_image_info[0]
                self.original_previous_height = previous_image_info[1]

            if self.animation_type == ANIMATION_TYPE_FLIP:
                self.animation_stage = "flip_out_current"
                self.current_display_image_ref = self.previous_image_surface
                self.target_width_for_flip = self.original_previous_width 
                self.target_height_for_flip = self.original_previous_height
                self._update_transform_for_flip()
            elif self.animation_type == ANIMATION_TYPE_CROSSFADE:
                self.animation_stage = "crossfade"
                self.current_alpha = 0 # Alpha for the new image (original_image)
                # We don't set current_x/y or call _update_single_image_transform here
                # because the drawing for crossfade is handled manually with both images.
                # The _update_single_image_transform will be used when it transitions to scale_up
            else: # Default to ANIMATION_TYPE_SLIDE_IN if not explicitly set
                self.animation_type = ANIMATION_TYPE_SLIDE_IN
                self.animation_stage = "slide"
                self.current_y = 0
                self.current_scale = 1
                
                center_x_offset = (WINDOW_WIDTH - self.original_width) / 2 if self.original_width < WINDOW_WIDTH else 0
                
                self.slide_direction = random.choice(['left', 'right'])
                if self.slide_direction == 'left':
                    self.current_x = -WINDOW_WIDTH + center_x_offset
                else:
                    self.current_x = WINDOW_WIDTH + center_x_offset

                self._update_single_image_transform()

        elif self.kind == MOSAIC_KIND_MULTI_IMAGE:
            # to do: image mosaic stuff
            pass

    def set_fading_out_visuals(self, surface, rect):
        self.fading_out_surface = surface
        self.fading_out_rect = rect

    def _update_single_image_transform(self):
        display_width = max(1, int(self.original_width * self.current_scale))
        display_height = max(1, int(self.original_height * self.current_scale))
        self.current_display_surface = pygame.transform.smoothscale(self.original_image, (display_width, display_height))
        self.rect = self.current_display_surface.get_rect(topleft=(self.current_x, self.current_y))

    def _update_transform_for_flip(self):
        display_width = max(1, int(self.target_width_for_flip))
        display_height = max(1, int(self.target_height_for_flip))
        
        self.current_display_surface = pygame.transform.smoothscale(self.current_display_image_ref, (display_width, display_height))
        self.rect = self.current_display_surface.get_rect(center=(WINDOW_WIDTH / 2, WINDOW_HEIGHT / 2))


    def update(self, current_time):
        elapsed_in_stage = current_time - self.stage_start_time

        if self.kind == MOSAIC_KIND_SINGLE_IMAGE:
            if self.animation_type == ANIMATION_TYPE_SLIDE_IN:
                # Stage 1: Slide In
                if self.animation_stage == "slide":
                    progress = min(1.0, elapsed_in_stage / SLIDE_DURATION_MS)
                    eased_slide_progress = 0.5 - 0.5 * math.cos(progress * math.pi)

                    center_x_offset = (WINDOW_WIDTH - self.original_width) / 2 if self.original_width < WINDOW_WIDTH else 0

                    if self.slide_direction == 'left':
                        self.current_x = int(-WINDOW_WIDTH + (WINDOW_WIDTH * eased_slide_progress) + center_x_offset)
                    else: # 'right'
                        self.current_x = int(WINDOW_WIDTH - (WINDOW_WIDTH * eased_slide_progress) + center_x_offset)
                        
                    self._update_single_image_transform()
            
                    if progress >= 1.0:
                        self.animation_stage = "scale_up"
                        self.stage_start_time = current_time
                        self.current_x = (WINDOW_WIDTH - self.original_width) / 2 if self.original_width < WINDOW_WIDTH else 0
                        self.current_y = 0
                        self._update_single_image_transform()
            
                # Stage 2: Scale Up (Zoom In) for SLIDE_IN
                elif self.animation_stage == "scale_up":
                    progress = min(1.0, elapsed_in_stage / SCALE_DURATION_MS)
                    eased_scale_progress = 0.5 - 0.5 * math.cos(progress * math.pi)
                    self.current_scale = 1 + eased_scale_progress * SCALE_FACTOR

                    center_x_offset = (WINDOW_WIDTH - self.original_width) / 2 if self.original_width < WINDOW_WIDTH else 0

                    display_width = max(1, int(self.original_width * self.current_scale))
                    display_height = max(1, int(self.original_height * self.current_scale))
                    self.current_x = ((display_width - self.original_width) / 2 * -1) + center_x_offset
                    self.current_y = (display_height - self.original_height) / 2 * -1
                    
                    self._update_single_image_transform()
            
                    if progress >= 1.0:
                        self.animation_stage = "complete"
                        self.stage_start_time = current_time
                        self._update_single_image_transform()

            elif self.animation_type == ANIMATION_TYPE_FLIP:
                half_flip_duration = FLIP_DURATION_MS / 2

                if self.animation_stage == "flip_out_current":
                    progress = min(1.0, elapsed_in_stage / half_flip_duration)
                    eased_progress = math.sin(progress * math.pi / 2)

                    self.target_height_for_flip = int(self.original_previous_height * (1 - eased_progress))
                    if self.target_height_for_flip < 1: 
                        self.target_height_for_flip = 1
                    
                    self.current_display_image_ref = self.previous_image_surface
                    self.target_width_for_flip = self.original_previous_width
                    self._update_transform_for_flip()

                    if progress >= 1.0:
                        self.animation_stage = "flip_in_new"
                        self.stage_start_time = current_time
                        self.target_height_for_flip = 1 


                elif self.animation_stage == "flip_in_new":
                    progress = min(1.0, elapsed_in_stage / half_flip_duration)
                    eased_progress = math.sin(progress * math.pi / 2)

                    self.target_height_for_flip = int(self.original_height * eased_progress)
                    if self.target_height_for_flip < 1:
                        self.target_height_for_flip = 1
                    
                    self.current_display_image_ref = self.original_image
                    self.target_width_for_flip = self.original_width
                    self._update_transform_for_flip()

                    if progress >= 1.0:
                        self.animation_stage = "scale_up"
                        self.stage_start_time = current_time
                        self.current_scale = 1
                        
                        self.current_x = (WINDOW_WIDTH - self.original_width) / 2
                        self.current_y = (WINDOW_HEIGHT - self.original_height) / 2
                        
                        self._update_single_image_transform()


                elif self.animation_stage == "scale_up":
                    progress = min(1.0, elapsed_in_stage / SCALE_DURATION_MS)
                    eased_scale_progress = 0.5 - 0.5 * math.cos(progress * math.pi)
                    self.current_scale = 1 + eased_scale_progress * SCALE_FACTOR

                    scaled_width = int(self.original_width * self.current_scale)
                    scaled_height = int(self.original_height * self.current_scale)

                    self.current_x = (WINDOW_WIDTH / 2) - (scaled_width / 2)
                    self.current_y = (WINDOW_HEIGHT / 2) - (scaled_height / 2)
                    
                    self._update_single_image_transform()
            
                    if progress >= 1.0:
                        self.animation_stage = "complete"
                        self.stage_start_time = current_time
                        self._update_single_image_transform()

            # NEW: CROSSFADE animation
            elif self.animation_type == ANIMATION_TYPE_CROSSFADE:
                if self.animation_stage == "crossfade":
                    progress = min(1.0, elapsed_in_stage / CROSSFADE_DURATION_MS)
                    eased_progress = 0.5 - 0.5 * math.cos(progress * math.pi)
                    self.current_alpha = int(255 * eased_progress)

                    if progress >= 1.0:
                        self.animation_stage = "scale_up"
                        self.stage_start_time = current_time
                        self.current_scale = 1
                        
                        # Position for scale_up phase after cross-fade (centered)
                        self.current_x = (WINDOW_WIDTH - self.original_width) / 2
                        self.current_y = (WINDOW_HEIGHT - self.original_height) / 2
                        self._update_single_image_transform()
                
                elif self.animation_stage == "scale_up":
                    progress = min(1.0, elapsed_in_stage / SCALE_DURATION_MS)
                    eased_scale_progress = 0.5 - 0.5 * math.cos(progress * math.pi)
                    self.current_scale = 1 + eased_scale_progress * SCALE_FACTOR

                    scaled_width = int(self.original_width * self.current_scale)
                    scaled_height = int(self.original_height * self.current_scale)

                    self.current_x = (WINDOW_WIDTH / 2) - (scaled_width / 2)
                    self.current_y = (WINDOW_HEIGHT / 2) - (scaled_height / 2)
                    
                    self._update_single_image_transform()
            
                    if progress >= 1.0:
                        self.animation_stage = "complete"
                        self.stage_start_time = current_time
                        self._update_single_image_transform()


        elif self.kind == MOSAIC_KIND_MULTI_IMAGE:
            # Multi-image update logic goes here
            pass

    def draw(self, surface):
        """Draws the current display surface of the mosaic to the given surface."""
        # NEW: Custom drawing for cross-fade animation
        if self.animation_type == ANIMATION_TYPE_CROSSFADE and self.animation_stage == "crossfade":
            # Draw the fading out previous image at its *last known rendered size/position*
            # This uses the surface and rect passed via set_fading_out_visuals
            if self.fading_out_surface:
                self.fading_out_surface.set_alpha(255 - self.current_alpha) # Fades from 255 to 0
                surface.blit(self.fading_out_surface, self.fading_out_rect.topleft)

            # Draw the fading in new image at its *original size, centered*
            new_image_x = (WINDOW_WIDTH - self.original_width) / 2
            new_image_y = (WINDOW_HEIGHT - self.original_height) / 2
            
            # The original_image is already at its original dimensions
            self.original_image.set_alpha(self.current_alpha) # Fades from 0 to 255
            surface.blit(self.original_image, (new_image_x, new_image_y))
        else:
            # Normal drawing for slide-in, flip, or scale_up phases
            if self.current_display_surface:
                surface.blit(self.current_display_surface, self.rect)


if WITH_RESIZE:
    resize_all_images(IMAGE_FOLDER_URL, DESTINATION_FOLDER, WINDOW_WIDTH, WINDOW_HEIGHT)
else:
    if not SKIP_COPY:
        copy_folder(IMAGE_FOLDER_URL, DESTINATION_FOLDER)

load_images(DESTINATION_FOLDER)
current_image_idx = 0
# Initialize the first mosaic
current_display_mosaic = AnimatedMosaic(MOSAIC_KIND_SINGLE_IMAGE, [images_paths[current_image_idx]], animation_type=ANIMATION_TYPE_SLIDE_IN)
next_image_trigger_time = pygame.time.get_ticks() + SLIDE_DURATION_MS + SCALE_DURATION_MS + 1

while running:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                running = False
        if event.type == pygame.VIDEORESIZE:
            WINDOW_WIDTH, WINDOW_HEIGHT = event.size
            screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.RESIZABLE)
            
            if current_display_mosaic:
                current_display_mosaic = AnimatedMosaic(MOSAIC_KIND_SINGLE_IMAGE, [current_display_mosaic.image_url], animation_type=ANIMATION_TYPE_SLIDE_IN)
            
            background_mosaic = None
            
            next_image_trigger_time = pygame.time.get_ticks() + SLIDE_DURATION_MS + SCALE_DURATION_MS + 1


    screen.fill((0, 0, 0))

    current_time_ms = pygame.time.get_ticks()

    if background_mosaic and current_display_mosaic.animation_type == ANIMATION_TYPE_SLIDE_IN:
        background_mosaic.update(current_time_ms)
        background_mosaic.draw(screen)

    if current_display_mosaic:
        current_display_mosaic.update(current_time_ms)
        current_display_mosaic.draw(screen)
    
        if current_display_mosaic.animation_stage == "complete" and current_time_ms >= next_image_trigger_time:
            
            temp_finished_mosaic = current_display_mosaic 

            current_image_idx = (current_image_idx + 1) % len(images_paths)
            next_image_url = images_paths[current_image_idx]

            temp_next_image_for_check = pygame.image.load(next_image_url)
            next_image_width = temp_next_image_for_check.get_width()
            next_image_height = temp_next_image_for_check.get_height()
            del temp_next_image_for_check

            can_be_transition_animation = False
            if (temp_finished_mosaic.kind == MOSAIC_KIND_SINGLE_IMAGE and 
                temp_finished_mosaic.original_width == next_image_width and 
                temp_finished_mosaic.original_height == next_image_height):
                can_be_transition_animation = True
            
            new_animation_type = ANIMATION_TYPE_SLIDE_IN
            if can_be_transition_animation:
                new_animation_type = random.choice([ANIMATION_TYPE_FLIP, ANIMATION_TYPE_CROSSFADE])
            
            if new_animation_type == ANIMATION_TYPE_FLIP or new_animation_type == ANIMATION_TYPE_CROSSFADE:
                background_mosaic = None 
            else:
                background_mosaic = temp_finished_mosaic

            if new_animation_type == ANIMATION_TYPE_FLIP:
                previous_image_info = (temp_finished_mosaic.original_width, 
                                       temp_finished_mosaic.original_height,
                                       temp_finished_mosaic.image_url)
                current_display_mosaic = AnimatedMosaic(MOSAIC_KIND_SINGLE_IMAGE, [next_image_url], animation_type=ANIMATION_TYPE_FLIP, previous_image_info=previous_image_info)
                next_image_trigger_time = current_time_ms + FLIP_DURATION_MS + SCALE_DURATION_MS + 1 
            elif new_animation_type == ANIMATION_TYPE_CROSSFADE:
                previous_image_info = (temp_finished_mosaic.original_width, 
                                       temp_finished_mosaic.original_height,
                                       temp_finished_mosaic.image_url)
                current_display_mosaic = AnimatedMosaic(MOSAIC_KIND_SINGLE_IMAGE, [next_image_url], animation_type=ANIMATION_TYPE_CROSSFADE, previous_image_info=previous_image_info)
                # NEW: Pass the previous image's final rendered state to the new mosaic
                current_display_mosaic.set_fading_out_visuals(temp_finished_mosaic.current_display_surface,
                                                               temp_finished_mosaic.rect)
                next_image_trigger_time = current_time_ms + CROSSFADE_DURATION_MS + SCALE_DURATION_MS + 1
            else:
                current_display_mosaic = AnimatedMosaic(MOSAIC_KIND_SINGLE_IMAGE, [next_image_url], animation_type=ANIMATION_TYPE_SLIDE_IN)
                next_image_trigger_time = current_time_ms + SLIDE_DURATION_MS + SCALE_DURATION_MS + 1


    print_date()
    print_time()

    actual_fps = clock.get_fps()
    fps_text_surface, fps_rect = font_small.render(f"FPS: {int(actual_fps)}", TEXT_COLOR)
    screen.blit(fps_text_surface, (TEXT_PADDING, TEXT_PADDING))

    pygame.display.flip()
    clock.tick(120)

pygame.quit()

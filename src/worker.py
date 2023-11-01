from logging import Logger
from threading import Thread
import time
from typing import Callable, Union

import cv2
import depthai as dai
from depthai_sdk import OakCamera
from depthai_sdk.classes.packets import PointcloudPacket
from depthai_sdk.components.camera_component import CameraComponent
from depthai_sdk.components.pointcloud_component import PointcloudComponent
from depthai_sdk.components.stereo_component import StereoComponent
import numpy as np
from numpy.typing import NDArray

RGB_STREAM_NAME = 'rgb'
DEPTH_STREAM_NAME = 'depth'
RIGHT_STREAM_NAME = 'right'
LEFT_STREAM_NAME = 'left'

class WorkerManager(Thread):
    def __init__(self,
                logger: Logger,
                reconfigure: Callable[[None], None],
                ) -> None:
        self.logger = logger
        self.needs_reconfigure = False
        self.running = True
        self.reconfigure = reconfigure
        super().__init__()
    
    def run(self):
        self.logger.debug('Starting worker manager.')
        while self.running:
            self.logger.debug('Checking if worker must be reconfigured.')
            if self.needs_reconfigure:
                self.logger.debug('Worker needs reconfiguring; reconfiguring worker.')
                self.reconfigure()
            time.sleep(5)

    def stop(self):
        self.logger.debug('Stopping worker manager.')
        self.running = False


class Worker(Thread):
    color_image: NDArray
    depth_map: NDArray
    manager: WorkerManager

    def __init__(self,
                height: int,
                width: int,
                frame_rate: float,
                should_get_color,
                should_get_depth,
                reconfigure: Callable[[None], None],
                logger: Logger,
                ) -> None:
        logger.info('Initializing camera pipeline worker.')

        self.height = height
        self.width = width
        self.frame_rate = frame_rate
        self.should_get_color = should_get_color
        self.should_get_depth = should_get_depth
        self.logger = logger

        self.color_image = np.array([])
        self.depth_map = np.array([])
        self.pcd = np.array([])

        self.manager = WorkerManager(logger, reconfigure)
        self.manager.start()
        super().__init__()
 
    def get_color_image(self) -> NDArray:
        return self.color_image
    
    def get_depth_map(self) -> NDArray:
        return self.depth_map
    
    def get_pcd(self) -> NDArray:
        return self.pcd

    def _pipeline_loop(self) -> None:
        failures = 0
        try:
            self.logger.debug('Initializing worker image pipeline.')
            with OakCamera() as oak:
                color = self._add_camera_rgb_node(oak)
                stereo = self._add_depth_node(oak, color)
                self._add_pc_node(oak, color, stereo)
                
                oak.start(blocking=False)
                while self.manager.running:
                    self._handle_color_output(oak)
                    self._handle_depth_output(oak)
                    self._handle_pcd_output(oak)
        except Exception as e:
            failures += 1
            if failures > 3:
                self.manager.needs_reconfigure = True
                self.logger.error(f"Exceeded max failures on pipeline loop. Error: {e}")
            else:
                self.logger.debug(f"Pipeline failure count: {failures}: Error: {e}")
        finally:
            self.logger.debug('Exiting worker camera loop.')

    def run(self) -> None:
        try:
            while self.manager.running:
                self._pipeline_loop()
        finally:
            self.logger.info('Stopped and exited worker thread.')

    def stop(self) -> None:
        self.logger.info('Stopping worker.')
        self.manager.stop()
    
    def _add_camera_rgb_node(self, oak: OakCamera) -> Union[CameraComponent, None] :
        if self.should_get_color:
            self.logger.debug('Creating pipeline node: color camera.')
            xout_color = oak.pipeline.create(dai.node.XLinkOut)
            xout_color.setStreamName(RGB_STREAM_NAME)
            color = oak.camera('color', fps=self.frame_rate)
            color.node.setPreviewSize(self.width, self.height)
            color.node.preview.link(xout_color.input)
            return color

    def _add_depth_node(self, oak: OakCamera, color: CameraComponent) -> Union[StereoComponent, None]:
        if self.should_get_depth:
            self.logger.debug('Creating pipeline node: stereo depth.')
            mono_right = oak.pipeline.create(dai.node.MonoCamera)
            mono_left = oak.pipeline.create(dai.node.MonoCamera)

            depth_out = oak.pipeline.create(dai.node.XLinkOut)
            depth_out.setStreamName(DEPTH_STREAM_NAME)
            xout_right = oak.pipeline.create(dai.node.XLinkOut)
            xout_right.setStreamName(RIGHT_STREAM_NAME)
            xout_left = oak.pipeline.create(dai.node.XLinkOut)
            xout_left.setStreamName(LEFT_STREAM_NAME)

            stereo = oak.stereo(fps=self.frame_rate, left=mono_left, right=mono_right)
            if self.should_get_color:
                stereo.config_stereo(align=color)
            stereo.node.depth.link(depth_out.input)
            return stereo

    def _add_pc_node(self, oak: OakCamera, color: CameraComponent, stereo: StereoComponent) -> Union[PointcloudComponent, None]:
        if self.should_get_depth:
            pcl = oak.create_pointcloud(stereo=stereo, colorize=color)
            oak.callback(pcl, callback=self._set_current_pcd)
            return pcl
    
    def _handle_color_output(self, oak: OakCamera) -> None:
        if self.should_get_color:
            rgb_queue = oak.device.getOutputQueue(RGB_STREAM_NAME)
            rgb_frame_data = rgb_queue.tryGet()
            if rgb_frame_data:
                bgr_frame = rgb_frame_data.getCvFrame()  # OpenCV uses reversed (BGR) color order
                rgb_frame = cv2.cvtColor(bgr_frame, cv2.COLOR_BGR2RGB)
                self._set_current_image(rgb_frame)
    
    def _handle_depth_output(self, oak: OakCamera) -> None:
        if self.should_get_depth:
            q_depth = oak.device.getOutputQueue(DEPTH_STREAM_NAME, maxSize=4, blocking=False)
            depth_frame = q_depth.tryGet()
            if depth_frame:
                np_depth_arr = depth_frame.getCvFrame()
                np_depth_arr = cv2.resize(np_depth_arr, (self.width, self.height))
                self._set_current_depth_map(np_depth_arr)
    
    def _handle_pcd_output(self, oak: OakCamera) -> None:
        if self.should_get_depth:
            oak.poll()

    def _set_current_image(self, arr: NDArray) -> None:
        self.logger.debug('Setting current_image.')
        self.color_image = arr

    def _set_current_depth_map(self, arr: NDArray) -> None:
        self.logger.debug('Setting current depth map.')
        self.depth_map = arr

    def _set_current_pcd(self, packet: PointcloudPacket) -> None:
        self.logger.debug('Setting current pcd.')
        self.pcd = packet.points

"""macOS camera access through AVFoundation.

OpenCV can only open a camera by index, and the index order was seen to change between
runs, which would silently swap the two identical Facecams. Devices are therefore opened
by uniqueID, and joined to the USB serial so an assignment survives a change of port.
"""
import json
import subprocess

import AVFoundation as AV
import CoreMedia as CM
import numpy as np
import objc
import Quartz
from Foundation import NSObject
from dispatch import dispatch_queue_create

from .base import CameraInfo, CameraMode, LatestFrame

BGRA = 1111970369  # kCVPixelFormatType_32BGRA


class CameraOpenError(Exception):
    pass


def usb_devices() -> dict[str, dict]:
    """USB video candidates by location id, for example '00200000'."""
    output = subprocess.run(
        ["system_profiler", "-json", "SPUSBHostDataType"], capture_output=True, text=True, timeout=20
    ).stdout
    found: dict[str, dict] = {}

    def walk(node) -> None:
        if isinstance(node, dict):
            location = node.get("USBKeyLocationID")
            if location:
                found[location.removeprefix("0x").lower().zfill(8)] = node
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(json.loads(output or "{}"))
    return found


def location_from_unique_id(unique_id: str) -> str | None:
    # UVC ids look like 0x<location><vendor:4><product:4>, for example 0x2000000fd90092.
    if not unique_id.startswith("0x") or len(unique_id) <= 10:
        return None
    return unique_id[2:-8].lower().zfill(8)


def device_modes(device) -> list[CameraMode]:
    modes: dict[tuple[int, int], set[float]] = {}
    for fmt in device.formats():
        size = CM.CMVideoFormatDescriptionGetDimensions(fmt.formatDescription())
        rates = modes.setdefault((size.width, size.height), set())
        rates.update(round(r.maxFrameRate(), 2) for r in fmt.videoSupportedFrameRateRanges())
    return [CameraMode(width=w, height=h, fps=sorted(fps)) for (w, h), fps in sorted(modes.items())]


def _capture_devices() -> list:
    # External only: Continuity iPhones report a separate device type and stay out of the list.
    session = AV.AVCaptureDeviceDiscoverySession.discoverySessionWithDeviceTypes_mediaType_position_(
        [AV.AVCaptureDeviceTypeExternal], AV.AVMediaTypeVideo, AV.AVCaptureDevicePositionUnspecified
    )
    return [d for d in session.devices() if d.modelID().startswith("UVC")]


def discover() -> list[CameraInfo]:
    usb = usb_devices()
    cameras = []
    for device in _capture_devices():
        unique_id = str(device.uniqueID())
        node = usb.get(location_from_unique_id(unique_id) or "", {})
        serial = node.get("USBDeviceKeySerialNumber")
        cameras.append(
            CameraInfo(
                key=serial or unique_id,
                device_id=unique_id,
                name=str(device.localizedName()),
                serial=serial,
                usb_speed=node.get("USBDeviceKeyLinkSpeed"),
                modes=device_modes(device),
            )
        )
    return cameras


class _FrameDelegate(NSObject):
    def initWithBuffer_(self, buffer):
        self = objc.super(_FrameDelegate, self).init()
        self.buffer = buffer
        return self

    def captureOutput_didOutputSampleBuffer_fromConnection_(self, output, sample, connection):
        pixels = CM.CMSampleBufferGetImageBuffer(sample)
        Quartz.CVPixelBufferLockBaseAddress(pixels, Quartz.kCVPixelBufferLock_ReadOnly)
        try:
            height = Quartz.CVPixelBufferGetHeight(pixels)
            width = Quartz.CVPixelBufferGetWidth(pixels)
            stride = Quartz.CVPixelBufferGetBytesPerRow(pixels)
            base = Quartz.CVPixelBufferGetBaseAddress(pixels)
            raw = np.frombuffer(base.as_buffer(stride * height), np.uint8).reshape(height, stride // 4, 4)
            # Copy out: the pixel buffer is reused by AVFoundation once this callback returns.
            self.buffer.put(raw[:, :width, :3].copy())
        finally:
            Quartz.CVPixelBufferUnlockBaseAddress(pixels, Quartz.kCVPixelBufferLock_ReadOnly)


class MacCameraCapture:
    def __init__(self, device_id: str, width: int = 1920, height: int = 1080, fps: float = 30.0):
        self.device_id = device_id
        self.width, self.height, self.fps = width, height, fps
        self.buffer = LatestFrame()
        self._session = None
        self._delegate = None
        self._frame_duration = None

    def _select_format(self, device) -> None:
        for fmt in device.formats():
            size = CM.CMVideoFormatDescriptionGetDimensions(fmt.formatDescription())
            if (size.width, size.height) != (self.width, self.height):
                continue
            for rate in fmt.videoSupportedFrameRateRanges():
                # UVC cameras report rates such as 29.97 or 30.00003, never an exact 30.
                if rate.minFrameRate() - 0.1 <= self.fps <= rate.maxFrameRate() + 0.1:
                    ok, error = device.lockForConfiguration_(None)
                    if not ok:
                        raise CameraOpenError(str(error))
                    device.setActiveFormat_(fmt)
                    device.unlockForConfiguration()
                    self._frame_duration = rate.minFrameDuration()
                    return
        raise CameraOpenError(f"{self.width}x{self.height} bij {self.fps:g} FPS wordt niet ondersteund")

    def _apply_frame_rate(self, device) -> None:
        ok, error = device.lockForConfiguration_(None)
        if not ok:
            raise CameraOpenError(str(error))
        device.setActiveVideoMinFrameDuration_(self._frame_duration)
        device.setActiveVideoMaxFrameDuration_(self._frame_duration)
        device.unlockForConfiguration()

    def start(self) -> None:
        device = AV.AVCaptureDevice.deviceWithUniqueID_(self.device_id)
        if device is None:
            raise CameraOpenError("camera niet gevonden")
        session = AV.AVCaptureSession.alloc().init()
        session.beginConfiguration()
        camera_input, error = AV.AVCaptureDeviceInput.deviceInputWithDevice_error_(device, None)
        if camera_input is None:
            raise CameraOpenError(str(error))
        session.addInput_(camera_input)
        output = AV.AVCaptureVideoDataOutput.alloc().init()
        output.setVideoSettings_({"PixelFormatType": BGRA})
        output.setAlwaysDiscardsLateVideoFrames_(True)
        self._delegate = _FrameDelegate.alloc().initWithBuffer_(self.buffer)
        output.setSampleBufferDelegate_queue_(self._delegate, dispatch_queue_create(self.device_id.encode(), None))
        session.addOutput_(output)
        self._select_format(device)
        session.commitConfiguration()
        session.startRunning()
        # Starting the session restores the format's default rate, so set it afterwards.
        self._apply_frame_rate(device)
        self._session = session

    def stop(self) -> None:
        if self._session is not None:
            self._session.stopRunning()
            self._session = None


Capture = MacCameraCapture

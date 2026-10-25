"""Complete-frame and caption clearance contracts at extreme artist settings."""
import unittest

from canvas_layout import anchor_rect


class CanvasGeometryTests(unittest.TestCase):
    def test_reference_never_stretches_or_leaves_canvas(self):
        for width,height in [(1280,720),(720,1280)]:
            for aspect in [16/9,1,9/16]:
                for x,y in [(-100,-100),(100,100),(.5,.5)]:
                    for requested in [0,.5,100]:
                        cx,cy,w,h=anchor_rect(width,height,aspect,x,y,requested,.2)
                        self.assertAlmostEqual(w*width/(h*height),aspect)
                        self.assertGreaterEqual(cx-w/2,.02-1e-12)
                        self.assertLessEqual(cx+w/2,.98+1e-12)
                        self.assertGreaterEqual(cy-h/2,.22-1e-12)
                        self.assertLessEqual(cy+h/2,.98+1e-12)

    def test_portrait_retains_entire_wide_frame(self):
        x,y,w,h=anchor_rect(720,1280,16/9,.5,.58,.9,.2)
        self.assertAlmostEqual(w*720,648)
        self.assertAlmostEqual(h*1280,364.5)


if __name__=='__main__':unittest.main()

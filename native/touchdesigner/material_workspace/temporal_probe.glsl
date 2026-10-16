// Synthetic native test signal: spatial gradients plus a moving color channel.
uniform vec4 uClock;
out vec4 fragColor;
void main() {
    fragColor=TDOutputSwizzle(vec4(vUV.x,vUV.y,.5+.4*sin(uClock.x*4.),.7));
}

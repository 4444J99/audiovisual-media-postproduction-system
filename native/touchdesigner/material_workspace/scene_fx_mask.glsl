uniform vec4 uAnchor;
uniform vec4 uCaption;
out vec4 fragColor;
void main(){
    vec2 uv=vUV.st;vec2 q=(uv-uAnchor.xy)/uAnchor.zw+.5;
    bool reference=all(greaterThanEqual(q,vec2(0)))&&all(lessThanEqual(q,vec2(1)));
    fragColor=TDOutputSwizzle(vec4(float(reference),float(uv.y<uCaption.x),0,1));
}

uniform vec4 uAnchor;
uniform vec4 uCaption;
out vec4 fragColor;
void main(){
    vec2 uv=vUV.st;vec2 q=(uv-uAnchor.xy)/uAnchor.zw+.5;
    bool reference=all(greaterThanEqual(q,vec2(0)))&&all(lessThanEqual(q,vec2(1)));
    vec4 p=texture(sTD2DInputs[0],uv);
    if(reference||uv.y<uCaption.x)p=texture(sTD2DInputs[1],uv);
    fragColor=TDOutputSwizzle(p);
}

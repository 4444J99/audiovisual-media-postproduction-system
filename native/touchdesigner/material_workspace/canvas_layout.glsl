// Auxiliary material is composited first. The complete reference is last.
uniform vec4 uAnchor;
uniform vec4 uCanvas;
uniform vec4 uBackground;
uniform vec4 uField0; uniform vec4 uField1; uniform vec4 uField2;
uniform vec4 uField3; uniform vec4 uField4;
uniform vec4 uCrop0; uniform vec4 uCrop1; uniform vec4 uCrop2;
uniform vec4 uCrop3; uniform vec4 uCrop4;
uniform vec4 uLook0; uniform vec4 uLook1; uniform vec4 uLook2;
uniform vec4 uLook3; uniform vec4 uLook4;
out vec4 fragColor;
vec4 Sample(int i,vec2 p) {
    if(any(lessThan(p,vec2(0)))||any(greaterThan(p,vec2(1))))return vec4(0);
    switch(i) {
        case 0:return texture(sTD2DInputs[0],p);
        case 1:return texture(sTD2DInputs[1],p);
        case 2:return texture(sTD2DInputs[2],p);
        case 3:return texture(sTD2DInputs[3],p);
        case 4:return texture(sTD2DInputs[4],p);
        case 5:return texture(sTD2DInputs[5],p);
        case 6:return texture(sTD2DInputs[6],p);
    }
    return vec4(0);
}
vec4 Over(vec4 a,vec4 b){return a+b*(1.-a.a);}
vec4 Field(int i,vec2 uv,vec4 rect,vec4 crop,vec4 look) {
    vec2 p=(uv-rect.xy)*uCanvas.xy;
    float a=radians(-look.x);
    p=mat2(cos(a),-sin(a),sin(a),cos(a))*p;
    vec2 q=p/(rect.zw*uCanvas.xy)+.5;
    if(any(lessThan(q,vec2(0)))||any(greaterThan(q,vec2(1))))return vec4(0);
    return Sample(i,crop.xy+q*crop.zw)*look.y;
}
void main() {
    vec2 uv=vUV.st;
    vec4 picture=uBackground;
    picture=Over(Field(1,uv,uField0,uCrop0,uLook0),picture);
    picture=Over(Field(2,uv,uField1,uCrop1,uLook1),picture);
    picture=Over(Field(3,uv,uField2,uCrop2,uLook2),picture);
    picture=Over(Field(4,uv,uField3,uCrop3,uLook3),picture);
    picture=Over(Field(5,uv,uField4,uCrop4,uLook4),picture);
    if(uv.y<uCanvas.z)picture=Over(Sample(6,vec2(uv.x,uv.y/uCanvas.z)),picture);
    vec2 q=(uv-uAnchor.xy)/uAnchor.zw+.5;
    if(all(greaterThanEqual(q,vec2(0)))&&all(lessThanEqual(q,vec2(1))))picture=Sample(0,q);
    fragColor=TDOutputSwizzle(picture);
}

uniform vec4 uCanvas;
uniform vec4 uBackground;
uniform vec4 uField0; uniform vec4 uField1; uniform vec4 uField2; uniform vec4 uField3; uniform vec4 uField4;
uniform vec4 uCrop0; uniform vec4 uCrop1; uniform vec4 uCrop2; uniform vec4 uCrop3; uniform vec4 uCrop4;
uniform vec4 uLook0; uniform vec4 uLook1; uniform vec4 uLook2; uniform vec4 uLook3; uniform vec4 uLook4;
out vec4 fragColor;
vec4 sampleField(int i,vec2 p){
    switch(i){case 1:return texture(sTD2DInputs[1],p);case 2:return texture(sTD2DInputs[2],p);case 3:return texture(sTD2DInputs[3],p);case 4:return texture(sTD2DInputs[4],p);case 5:return texture(sTD2DInputs[5],p);}return vec4(0);
}
vec4 field(int i,vec2 uv,vec4 rect,vec4 crop,vec4 look){
    vec2 p=(uv-rect.xy)*uCanvas.xy;float a=radians(-look.x);p=mat2(cos(a),-sin(a),sin(a),cos(a))*p;
    vec2 q=p/(rect.zw*uCanvas.xy)+.5;
    if(any(lessThan(q,vec2(0)))||any(greaterThan(q,vec2(1))))return vec4(0);
    return sampleField(i,crop.xy+q*crop.zw)*look.y;
}
vec4 over(vec4 a,vec4 b){return a+b*(1.-a.a);}
void main(){vec2 uv=vUV.st;vec4 p=uBackground;
    p=over(field(1,uv,uField0,uCrop0,uLook0),p);p=over(field(2,uv,uField1,uCrop1,uLook1),p);p=over(field(3,uv,uField2,uCrop2,uLook2),p);p=over(field(4,uv,uField3,uCrop3,uLook3),p);p=over(field(5,uv,uField4,uCrop4,uLook4),p);
    fragColor=TDOutputSwizzle(p);
}

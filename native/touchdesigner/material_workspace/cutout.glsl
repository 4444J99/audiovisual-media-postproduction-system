out vec4 fragColor;
void main(){vec4 p=texture(sTD2DInputs[0],vUV.st);float a=texture(sTD2DInputs[1],vUV.st).r;fragColor=TDOutputSwizzle(vec4(p.rgb*a,a));}

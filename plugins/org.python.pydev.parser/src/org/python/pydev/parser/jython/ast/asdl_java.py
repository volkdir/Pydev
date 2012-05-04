"""Generate Java code from an ASDL description."""

# TO DO
# handle fields that have a type but no name

import os, sys, traceback

import asdl

TABSIZE = 4
MAX_COL = 100

def reflow_lines(s, depth):
    """Reflow the line s indented depth tabs.

    Return a sequence of lines where no line extends beyond MAX_COL
    when properly indented.  The first line is properly indented based
    exclusively on depth * TABSIZE.  All following lines -- these are
    the reflowed lines generated by this function -- start at the same
    column as the first character beyond the opening { in the first
    line.
    """
    size = MAX_COL - depth * TABSIZE
    if len(s) < size:
        return [s]

    lines = []
    cur = s
    padding = ""
    while len(cur) > size:
        i = cur.rfind(' ', 0, size)
        assert i != -1, "Impossible line to reflow: %s" % `s`
        lines.append(padding + cur[:i])
        if len(lines) == 1:
            # find new size based on brace
            j = cur.find('{', 0, i)
            if j >= 0:
                j += 2 # account for the brace and the space after it
                size -= j
                padding = " " * j
        cur = cur[i+1:]
    else:
        lines.append(padding + cur)
    return lines

class EmitVisitor(asdl.VisitorBase):
    """Visit that emits lines"""

    def __init__(self):
        super(EmitVisitor, self).__init__()

    def open(self, name, refersToSimpleNode=1, useDataOutput=0):
        self.file = open("%s.java" % name, "wb")
        self.file.write("// Autogenerated AST node\n")
        self.file.write('package org.python.pydev.parser.jython.ast;\n')
        if refersToSimpleNode:
            self.file.write('import org.python.pydev.parser.jython.SimpleNode;\n')
            self.file.write('import java.util.Arrays;\n')
#        if useDataOutput:
#            print >> self.file, 'import java.io.DataOutputStream;'
#            print >> self.file, 'import java.io.IOException;'
        self.file.write('\n')
    
    def close(self):
        self.file.close()

    def emit(self, s, depth):
        # XXX reflow long lines?
        lines = reflow_lines(s, depth)
        for line in lines:
            line = (" " * TABSIZE * depth) + line + "\n"
            self.file.write(line)



# This step will add a 'simple' boolean attribute to all Sum and Product 
# nodes and add a 'typedef' link to each Field node that points to the
# Sum or Product node that defines the field.

class AnalyzeVisitor(EmitVisitor):
    index = 0
    def makeIndex(self):
        self.index += 1
        return self.index

    def visitModule(self, mod):
        self.types = {}
        for dfn in mod.dfns:
            self.types[str(dfn.name)] = dfn.value
        for dfn in mod.dfns:
            self.visit(dfn)

    def visitType(self, type, depth=0):
        self.visit(type.value, type.name, depth)

    def visitSum(self, sum, name, depth):
        sum.simple = 1
        for t in sum.types:
            if t.fields:
                sum.simple = 0
                break
        for t in sum.types:
            if not sum.simple:
                t.index = self.makeIndex()
            self.visit(t, name, depth)

    def visitProduct(self, product, name, depth):
        product.simple = 0
        product.index = self.makeIndex()
        for f in product.fields:
            self.visit(f, depth + 1)

    def visitConstructor(self, cons, name, depth):
        for f in cons.fields:
            self.visit(f, depth + 1)

    def visitField(self, field, depth):
        field.typedef = self.types.get(str(field.type))



# The code generator itself.
#
class JavaVisitor(EmitVisitor):
    def visitModule(self, mod):
        for dfn in mod.dfns:
            self.visit(dfn)

    def visitType(self, type, depth=0):
        self.visit(type.value, type.name, depth)

    def visitSum(self, sum, name, depth):
        if sum.simple:
            self.simple_sum(sum, name, depth)
        else:
            self.sum_with_constructor(sum, name, depth)

    def simple_sum(self, sum, name, depth):
        self.open("%sType" % name, refersToSimpleNode=0)
        self.emit("public interface %(name)sType {" % locals(), depth)
        for i in range(len(sum.types)):
            type = sum.types[i]
            self.emit("public static final int %s = %d;" % (type.name, i+1),
                                                    depth + 1)
        self.emit("", 0)
        self.emit("public static final String[] %sTypeNames = new String[] {" % 
                    name, depth+1)
        self.emit('"<undef>",', depth+2)
        for type in sum.types:
            self.emit('"%s",' % type.name, depth+2)
        self.emit("};", depth+1)
        self.emit("}", depth)
        self.close()
   
    def sum_with_constructor(self, sum, name, depth):
        self.open("%sType" % name)
        self.emit("public abstract class %(name)sType extends SimpleNode {" %
                    locals(), depth)
        
        #fabioz: HACK WARNING: Moved the suite body to suiteType!
        if str(name) == 'suite':
            self.emit("public stmtType[] body;", depth+1)
        #HACK WARNING: Moved the suite body to suiteType!
            
        self.emit("}", depth)
        self.close()
        for t in sum.types:
            self.visit(t, name, depth)

    def visitProduct(self, product, name, depth):
        self.open("%sType" % name, useDataOutput=1)
        self.emit("public final class %(name)sType extends SimpleNode {" % locals(), depth)
        for f in product.fields:
            self.visit(f, depth + 1)
        self.emit("", depth)

        self.javaMethods(product, name, "%sType" % name, product.fields,
                         depth+1)

        self.emit("}", depth)
        self.close()

    def visitConstructor(self, cons, name, depth):
        self.open(cons.name, useDataOutput=1)
        enums = []
        for f in cons.fields:
            if f.typedef and f.typedef.simple:
                enums.append("%sType" % f.type)
        if enums:
            s = "implements %s " % ", ".join(enums)
        else:
            s = ""
        self.emit("public final class %s extends %sType %s{" %
                    (cons.name, name, s), depth)
        
        #fabioz: HACK WARNING: Moved the suite body to suiteType!
        if str(name) != 'suite':
            for f in cons.fields:
                self.visit(f, depth + 1)
        #HACK WARNING: Moved the suite body to suiteType!
        
        self.emit("", depth)

        self.javaMethods(cons, cons.name, cons.name, cons.fields, depth+1)

        self.emit("}", depth)
        self.close()

    def javaMethods(self, type, clsname, ctorname, fields, depth):
        # The java ctors
        fpargs = ", ".join([self.fieldDef(f) for f in fields])

        self.emit("public %s(%s) {" % (ctorname, fpargs), depth)
        
        for f in fields:
            self.emit("this.%s = %s;" % (f.name, f.name), depth+1)
                
        if str(ctorname) == 'Suite':
            self.emit("if(body != null && body.length > 0){", depth+1)
            self.emit("beginColumn = body[0].beginColumn;", depth+2)
            self.emit("beginLine = body[0].beginLine;", depth+2)
            self.emit("}", depth+1)
            
        self.emit("}", depth)
        self.emit("", 0)

        if fpargs:
            fpargs += ", "
            

#fabioz: Removed the consructor with the parent that set the beginLine/Col, as this wasn't used and added some
#confusion because the parent wasn't properly set -- if a parent is actually set, it's set later in the parsing (because
#the parent is resolved after the child).
#        Creates something as:            
#        public Attribute(exprType value, NameTokType attr, int ctx, SimpleNode
#        parent) {
#            this(value, attr, ctx);
#            this.beginLine = parent.beginLine;
#            this.beginColumn = parent.beginColumn;
#        }

#        self.emit("public %s(%sSimpleNode parent) {" % (ctorname, fpargs), depth)
#        self.emit("this(%s);" %
#                    ", ".join([str(f.name) for f in fields]), depth+1)
#        self.emit("this.beginLine = parent.beginLine;", depth+1);
#        self.emit("this.beginColumn = parent.beginColumn;", depth+1);
#        self.emit("}", depth)
        self.emit("", 0)
        
     
        self.emit("public int hashCode() {", depth)
        self.emit("final int prime = 31;", depth+1)
        self.emit("int result = 1;", depth+1)
        for f in fields:
            jType = self.jType(f)
            if f.seq:
                self.emit("result = prime * result + Arrays.hashCode(%s);" % (f.name,), depth+1)
            elif jType == 'int':
                self.emit("result = prime * result + %s;" % (f.name,), depth+1)
            elif jType == 'boolean':
                self.emit("result = prime * result + (%s ? 17 : 137);" % (f.name,), depth+1)
            else:
                self.emit("result = prime * result + ((%s == null) ? 0 : %s.hashCode());" % (f.name, f.name), depth+1)
        self.emit("return result;", depth)
        self.emit("}", depth)
        
        #equals()
        self.emit("public boolean equals(Object obj) {", depth)
        self.emit("if (this == obj) return true;", depth+1)
        self.emit("if (obj == null) return false;", depth+1)
        self.emit("if (getClass() != obj.getClass()) return false;", depth+1)
        self.emit("%s other = (%s) obj;" % (ctorname, ctorname,), depth+1)
        for f in fields:
            jType = self.jType(f)
            if f.seq:
                self.emit('if (!Arrays.equals(%s, other.%s)) return false;' % (f.name, f.name,), depth+1) 
                
            elif jType in ('int', 'boolean'):
                self.emit('if(this.%s != other.%s) return false;' % (f.name, f.name,), depth+1) 
                
            else:
                self.emit('if (%s == null) { if (other.%s != null) return false;}' % (f.name, f.name,), depth+1) 
                self.emit('else if (!%s.equals(other.%s)) return false;' % (f.name, f.name,), depth+1) 
                
        self.emit("return true;", depth+1)
                
        self.emit("}", depth)
        
        
        #createCopy()
        self.emit("public %s createCopy() {" % (ctorname,), depth)
        self.emit("return createCopy(true);", depth+1)
        self.emit("}", depth)
        
        self.emit("public %s createCopy(boolean copyComments) {" % (ctorname,), depth)
        params = []
        copy_i = 0
        for f in fields:
            jType = self.jType(f)
            if jType in ('int', 'boolean', 'String', 'Object'):
                if f.seq:
                    self.emit('%s[] new%s;' % (jType,copy_i), depth+1) 
                    self.emit('if(this.%s != null){' % (f.name,), depth+1) 
                        
                    #int[] new0 = new int[this.ops.length];
                    #System.arraycopy(this.ops, 0, new0, 0, this.ops.length);
                    self.emit('new%s = new %s[this.%s.length];' % (copy_i, jType, f.name), depth+2) 
                    self.emit('System.arraycopy(this.%s, 0, new%s, 0, this.%s.length);' % (f.name, copy_i, f.name), depth+2) 
                    
                    self.emit('}else{', depth+1)
                    self.emit('new%s = this.%s;'%(copy_i, f.name), depth+2)
                    self.emit('}', depth+1)
                         
                    
                    params.append('new%s' % (copy_i,))
                    copy_i += 1
                else:
                    params.append(str(f.name))
            else:
                if f.seq:
                    #comprehensionType[] new0 = new comprehensionType[this.generators.length];
                    #for(int i=0;i<this.generators.length;i++){
                    #    new0[i] = (comprehensionType) this.generators[i] != null?this.generators[i].createCopy():null;
                    #}
                    self.emit('%s[] new%s;' % (jType,copy_i), depth+1) 
                    self.emit('if(this.%s != null){' % (f.name,), depth+1) 
                    self.emit('new%s = new %s[this.%s.length];' % (copy_i, jType, f.name), depth+1) 
                    self.emit('for(int i=0;i<this.%s.length;i++){' % (f.name), depth+1)
                    self.emit('new%s[i] = (%s) (this.%s[i] != null? this.%s[i].createCopy(copyComments):null);' % (copy_i, jType, f.name, f.name), depth+2) 
                    self.emit('}', depth+1)
                    self.emit('}else{', depth+1)
                    self.emit('new%s = this.%s;'%(copy_i, f.name), depth+2)
                    self.emit('}', depth+1)
                    
                    params.append('new%s' % (copy_i,))
                    copy_i += 1
                else:  
                    params.append('%s!=null?(%s)%s.createCopy(copyComments):null' % (f.name, jType, f.name))
            
        params = ", ".join(params)
        
        self.emit("%s temp = new %s(%s);" %
                    (ctorname, ctorname, params), depth+1)
        
        self.emit("temp.beginLine = this.beginLine;", depth+1);
        self.emit("temp.beginColumn = this.beginColumn;", depth+1);
        
        def EmitSpecials(s):
            self.emit('if(this.specials%s != null && copyComments){' % s, depth+1)
            self.emit('    for(Object o:this.specials%s){' % s, depth+1)
            self.emit('        if(o instanceof commentType){', depth+1)
            self.emit('            commentType commentType = (commentType) o;', depth+1)
            self.emit('            temp.getSpecials%s().add(commentType.createCopy(copyComments));' %s, depth+1)
            self.emit('        }', depth+1)
            self.emit('    }', depth+1)
            self.emit('}', depth+1)
        
        EmitSpecials('Before')
        EmitSpecials('After')
        
        self.emit("return temp;", depth+1);
        self.emit("}", depth)
        self.emit("", 0)
        
        
        

        # The toString() method
        self.emit("public String toString() {", depth)
        self.emit('StringBuffer sb = new StringBuffer("%s[");' % clsname,
                    depth+1)
        for f in fields:
            self.emit('sb.append("%s=");' % f.name, depth+1)
            if not self.bltinnames.has_key(str(f.type)) and f.typedef.simple:
                self.emit("sb.append(dumpThis(this.%s, %sType.%sTypeNames));" %
                        (f.name, f.type, f.type), depth+1)
            else:
                self.emit("sb.append(dumpThis(this.%s));" % f.name, depth+1)
            if f != fields[-1]:
                self.emit('sb.append(", ");', depth+1)
        self.emit('sb.append("]");', depth+1)
        self.emit("return sb.toString();", depth+1)
        self.emit("}", depth)
        self.emit("", 0)

#        # The pickle() method -- commented out, as it's not used within Pydev 
#        self.emit("public void pickle(DataOutputStream ostream) throws IOException {", depth)
#        self.emit("pickleThis(%s, ostream);" % type.index, depth+1);
#        for f in fields:
#            self.emit("pickleThis(this.%s, ostream);" % f.name, depth+1)
#        self.emit("}", depth)
#        self.emit("", 0)

        # The accept() method
        self.emit("public Object accept(VisitorIF visitor) throws Exception {", depth)
        if clsname == ctorname:
            self.emit('return visitor.visit%s(this);' % clsname, depth+1)
        else:
            self.emit('traverse(visitor);' % clsname, depth+1)
            self.emit('return null;' % clsname, depth+1)
        self.emit("}", depth)
        self.emit("", 0)

        # The visitChildren() method
        self.emit("public void traverse(VisitorIF visitor) throws Exception {", depth)
        for f in fields:
            if self.bltinnames.has_key(str(f.type)):
                continue
            if f.typedef.simple:
                continue
            if f.seq:
                self.emit('if (%s != null) {' % f.name, depth+1)
                self.emit('for (int i = 0; i < %s.length; i++) {' % f.name,
                        depth+2)
                self.emit('if (%s[i] != null){' % f.name, depth+3)
                self.emit('%s[i].accept(visitor);' % f.name, depth+4)
                self.emit('}' % f.name, depth+3)
                self.emit('}', depth+2)
                self.emit('}', depth+1)
            else:
                self.emit('if (%s != null){' % f.name, depth+1)
                self.emit('%s.accept(visitor);' % f.name, depth+2)
                self.emit('}' % f.name, depth+1)
        self.emit('}', depth)
        self.emit("", 0)

    def visitField(self, field, depth):
        self.emit("public %s;" % self.fieldDef(field), depth)

    bltinnames = {
        'bool' : 'boolean',
        'int' : 'int',
        'identifier' : 'String',
        'string' : 'String',
        'object' : 'Object', # was PyObject
    }
    
    def jType(self, field):
        jtype = str(field.type)
        if field.typedef and field.typedef.simple:
            jtype = 'int'
        else:
            jtype = self.bltinnames.get(jtype, jtype + 'Type')
        return jtype

    def fieldDef(self, field):
        jtype = self.jType(field)
        name = field.name
        seq = field.seq and "[]" or ""
        return "%(jtype)s%(seq)s %(name)s" % locals()


class VisitorVisitor(EmitVisitor):
    def __init__(self):
        EmitVisitor.__init__(self)
        self.ctors = []
        

    def visitModule(self, mod):
        for dfn in mod.dfns:
            self.visit(dfn)
        self.open("VisitorIF", refersToSimpleNode=0)
        self.emit('public interface VisitorIF {', 0)
        for ctor in self.ctors:
            self.emit("public Object visit%s(%s node) throws Exception;" % 
                    (ctor, ctor), 1)
        self.emit('}', 0)
        self.close()

        self.open("ISimpleNodeSwitch", refersToSimpleNode=0)
        self.emit('public interface ISimpleNodeSwitch {', 0)
        for ctor in self.ctors:
            self.emit("public void visit(%s node);" % 
                    (ctor,), 1)
        self.emit('}', 0)
        self.close()

        self.open("VisitorBase")
        self.emit('public abstract class VisitorBase implements VisitorIF {', 0)
        for ctor in self.ctors:
            self.emit("public Object visit%s(%s node) throws Exception {" % 
                    (ctor, ctor), 1)
            self.emit("Object ret = unhandled_node(node);", 2)
            self.emit("traverse(node);", 2)
            self.emit("return ret;", 2)
            self.emit('}', 1)
            self.emit('', 0)

        self.emit("abstract protected Object unhandled_node(SimpleNode node) throws Exception;", 1)
        self.emit("abstract public void traverse(SimpleNode node) throws Exception;", 1)
        self.emit('}', 0)
        self.close()

    def visitType(self, type, depth=1):
        self.visit(type.value, type.name, depth)

    def visitSum(self, sum, name, depth):
        if not sum.simple:
            for t in sum.types:
                self.visit(t, name, depth)

    def visitProduct(self, product, name, depth):
        pass

    def visitConstructor(self, cons, name, depth):
        self.ctors.append(cons.name)



class ChainOfVisitors:
    def __init__(self, *visitors):
        self.visitors = visitors

    def visit(self, object):
        for v in self.visitors:
            v.visit(object)

if __name__ == "__main__":
    mod = asdl.parse(sys.argv[1])
    if not asdl.check(mod):
        sys.exit(1)
    c = ChainOfVisitors(AnalyzeVisitor(),
                        JavaVisitor(),
                        VisitorVisitor())
    c.visit(mod)

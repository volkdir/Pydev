/**
 * Copyright: Fabio Zadrozny
 * License: EPL
 */
package org.python.pydev.shared_core.auto_edit;

import java.io.IOException;
import java.util.Iterator;
import java.util.LinkedList;
import java.util.List;

import org.eclipse.jface.text.BadLocationException;
import org.eclipse.jface.text.BadPositionCategoryException;
import org.eclipse.jface.text.IDocument;
import org.eclipse.jface.text.Position;
import org.eclipse.jface.text.TypedPosition;
import org.python.pydev.shared_core.log.Log;

/**
 * A reader that'll only read based on a given partition type.
 * 
 * @author Fabio Zadrozny
 */
public class PartitionCodeReader {

    /** The EOF character */
    public static final int EOF = -1;

    private boolean fForward = false;

    private IDocument fDocument;
    private int fOffset;

    private int fEnd = -1;

    private final String contentType;

    private List<Position> fPositions;

    public PartitionCodeReader(String contentType) {
        this.contentType = contentType;
    }

    /**
     * Returns the offset of the last read character. Should only be called after read has been called.
     */
    public int getOffset() {
        return fForward ? fOffset - 1 : fOffset;
    }

    public void configureForwardReader(IDocument document, int offset, int end) throws IOException,
            BadPositionCategoryException {
        fDocument = document;
        fOffset = offset;
        fForward = true;
        fEnd = Math.min(fDocument.getLength(), end);
        fPositions = createPositions(document);
    }

    private List<Position> createPositions(IDocument document) throws BadPositionCategoryException {
        Position[] positions;
        try {
            positions = document.getPositions(contentType);
        } catch (BadPositionCategoryException e) {
            Log.log("Unable to get positions for: " + contentType, e); //Shouldn't happen, but if it does, consider the whole doc.
            positions = new Position[] { new TypedPosition(0, document.getLength(), contentType) };
        }
        LinkedList<Position> list = new LinkedList<Position>();
        for (int i = 0; i < positions.length; i++) {
            Position position = positions[i];
            if (isPositionValid(position)) {
                list.add(position);
            }
        }

        return list;
    }

    private boolean isPositionValid(Position position) {
        if (fForward) {
            if (position.getOffset() + position.getLength() >= fOffset) {
                return true;
            }
        } else {
            if (position.getOffset() <= fOffset) {
                return true;
            }
        }
        return false;
    }

    public void configureBackwardReader(IDocument document, int offset) throws IOException,
            BadPositionCategoryException {
        fDocument = document;
        fOffset = offset;
        fForward = false;
        fPositions = createPositions(document);
    }

    /*
     * @see Reader#close()
     */
    public void close() throws IOException {
        fDocument = null;
    }

    /*
     * @see SingleCharReader#read()
     */
    public int read() throws IOException {
        try {
            return fForward ? readForwards() : readBackwards();
        } catch (BadLocationException x) {
            return EOF; //Document may have changed...
        }
    }

    private int readForwards() throws BadLocationException {
        while (fOffset < fEnd) {
            if (skip()) {
                fOffset++;
                continue;
            }
            char current = fDocument.getChar(fOffset);
            fOffset++;
            return current;
        }

        return EOF;
    }

    private int readBackwards() throws BadLocationException {
        while (fOffset > 0) {

            if (skip()) {
                --fOffset;
                continue;
            }
            char current = fDocument.getChar(fOffset);
            --fOffset;
            return current;

        }

        return EOF;
    }

    private boolean skip() {
        List<Position> positions = fPositions;
        Iterator<Position> iterator = positions.iterator();
        while (iterator.hasNext()) {
            Position position = iterator.next();
            if (position.getOffset() <= fOffset && position.getOffset() + position.getLength() > fOffset) {
                return false;
            } else {
                if (!isPositionValid(position)) {
                    iterator.remove();
                }
            }
        }
        return true;
    }
}
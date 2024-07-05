package com.example.t2pvalidation.utils;

import org.xml.sax.ErrorHandler;
import org.xml.sax.SAXException;
import org.xml.sax.SAXParseException;

import java.util.ArrayList;
import java.util.List;

public class CustomErrorHandler implements ErrorHandler {
    private final List<SAXParseException> syntaxErrors = new ArrayList<>();
    private final List<SAXParseException> syntaxWarnings = new ArrayList<>();

    @Override
    public void warning(SAXParseException exception) throws SAXException {
        syntaxWarnings.add(exception);
    }

    @Override
    public void error(SAXParseException exception) throws SAXException {
        syntaxErrors.add(exception);
    }

    @Override
    public void fatalError(SAXParseException exception) throws SAXException {
        syntaxErrors.add(exception);
    }

    public List<SAXParseException> getErrors() {
        return syntaxErrors;
    }

    public List<SAXParseException> getWarnings() {
        return syntaxWarnings;
    }
}

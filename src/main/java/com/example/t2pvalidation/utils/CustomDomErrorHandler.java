package com.example.t2pvalidation.utils;

import org.xml.sax.ErrorHandler;
import org.xml.sax.SAXException;
import org.xml.sax.SAXParseException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class CustomDomErrorHandler implements ErrorHandler {

    private static final Logger logger = LoggerFactory.getLogger(CustomDomErrorHandler.class);

    @Override
    public void warning(SAXParseException exception) throws SAXException {
        logger.warn("Warning at line " + exception.getLineNumber() + ": " + exception.getMessage());
    }

    @Override
    public void error(SAXParseException exception) throws SAXException {
        logger.error("Error at line " + exception.getLineNumber() + ": " + exception.getMessage());
    }

    @Override
    public void fatalError(SAXParseException exception) throws SAXException {
        logger.error("Fatal error at line " + exception.getLineNumber() + ": " + exception.getMessage());
    }
}

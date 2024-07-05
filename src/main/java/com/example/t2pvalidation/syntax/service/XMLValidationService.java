package com.example.t2pvalidation.syntax.service;

import com.example.t2pvalidation.utils.CustomErrorHandler;
import com.example.t2pvalidation.utils.ValidationResult;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.xml.sax.SAXException;

import javax.xml.XMLConstants;
import javax.xml.transform.stream.StreamSource;
import javax.xml.validation.Schema;
import javax.xml.validation.SchemaFactory;
import javax.xml.validation.Validator;
import java.io.File;
import java.io.IOException;
import java.util.ArrayList;
import java.util.List;

@Service
public class XMLValidationService {

    Logger logger = LoggerFactory.getLogger(XMLValidationService.class);

    public ValidationResult validateXml(String xmlFilePath, String xsdFilePath) {
        CustomErrorHandler errorHandler = new CustomErrorHandler();
        ValidationResult validationResult = new ValidationResult();

        try {
            SchemaFactory factory = SchemaFactory.newInstance(XMLConstants.W3C_XML_SCHEMA_NS_URI);
            Schema schema = factory.newSchema(new File(xsdFilePath));
            Validator validator = schema.newValidator();
            validator.setErrorHandler(errorHandler);
            validator.validate(new StreamSource(new File(xmlFilePath)));

            List<Object> errors = new ArrayList<>(errorHandler.getErrors());
            List<Object> warnings = new ArrayList<>(errorHandler.getWarnings());

            validationResult.setErrors(errors);
            validationResult.setWarnings(warnings);
            validationResult.setValidationStatus("completed");

        } catch (SAXException | IOException e) {
            logger.error("Validation error: ", e);
            validationResult.setValidationStatus("failed");
            validationResult.setErrorMessage(e.getMessage());

            List<Object> errors = new ArrayList<>(errorHandler.getErrors());
            validationResult.setErrors(errors);
        }

        return validationResult;
    }
}

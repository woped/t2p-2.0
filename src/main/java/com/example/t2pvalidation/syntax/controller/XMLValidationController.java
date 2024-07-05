package com.example.t2pvalidation.syntax.controller;

import com.example.t2pvalidation.syntax.service.XMLValidationService;
import com.example.t2pvalidation.utils.ValidationUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

@RestController
public class XMLValidationController {

    @Autowired
    private XMLValidationService xmlValidationService;

    private static final String XSD_FILE_PATH = "src/main/resources/BPMN20.xsd";

    @GetMapping("/xml_validate")
    public Map<String, Object> validateXml(@RequestParam String xmlFilePath) {
        var validationResult = xmlValidationService.validateXml(xmlFilePath, XSD_FILE_PATH);
        return ValidationUtils.mapValidationResult(validationResult);
    }
}

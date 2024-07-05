package com.example.t2pvalidation.syntax.controller;

import com.example.t2pvalidation.syntax.service.ValidationFlowService;
import com.example.t2pvalidation.utils.ValidationResult;
import com.example.t2pvalidation.utils.ValidationUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

@RestController
public class ValidationFlowController {

    @Autowired
    private ValidationFlowService validationFlowService;

    @GetMapping("/validate-flows")
    public Map<String, Object> validateFlows(@RequestParam String filePath) {
        ValidationResult validationResult = validationFlowService.validateNoUnboundFlows(filePath);
        return ValidationUtils.mapValidationResult(validationResult);
    }
}
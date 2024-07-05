package com.example.t2pvalidation.syntax.controller;

import com.example.t2pvalidation.syntax.service.GatewayValidationService;
import com.example.t2pvalidation.utils.ValidationResult;
import com.example.t2pvalidation.utils.ValidationUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

@RestController
public class GatewayValidationController {


    @Autowired
    private GatewayValidationService gatewayValidationService;

    @GetMapping("/validate-bpmn-gateway")
    public Map<String, Object> validateBpmn(String filePath) {

        ValidationResult validationResult = gatewayValidationService.validateGateways(filePath);
        return ValidationUtils.mapValidationResult(validationResult);
    }
}

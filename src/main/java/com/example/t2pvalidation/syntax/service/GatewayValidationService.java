package com.example.t2pvalidation.syntax.service;

import com.example.t2pvalidation.utils.ValidationResult;
import org.camunda.bpm.model.bpmn.Bpmn;
import org.camunda.bpm.model.bpmn.BpmnModelInstance;
import org.camunda.bpm.model.bpmn.instance.Gateway;
import org.camunda.bpm.model.bpmn.instance.SequenceFlow;
import org.camunda.bpm.model.bpmn.instance.ExclusiveGateway;
import org.camunda.bpm.model.bpmn.instance.InclusiveGateway;
import org.camunda.bpm.model.bpmn.instance.ComplexGateway;
import org.camunda.bpm.model.bpmn.instance.ParallelGateway;
import org.camunda.bpm.model.xml.ModelParseException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import java.io.File;
import java.util.ArrayList;
import java.util.Collection;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

@Service
public class GatewayValidationService {

    private static final Logger logger = LoggerFactory.getLogger(GatewayValidationService.class);

    public ValidationResult validateGateways(String bpmnFilePath) {
        ValidationResult validationResult = new ValidationResult();
        List<Object> errors = new ArrayList<>();
        List<Object> warnings = new ArrayList<>();

        BpmnModelInstance modelInstance = null;
        try {
            modelInstance = Bpmn.readModelFromFile(new File(bpmnFilePath));
        } catch (ModelParseException e) {
            logger.warn("Handled BPMN parsing issue: " + e.getMessage());
            warnings.add("BPMN parsing issues detected: " + e.getMessage());
            validationResult.setWarnings(warnings);
        }

        if (modelInstance != null) {
            try {
                Collection<Gateway> gateways = modelInstance.getModelElementsByType(Gateway.class);
                Map<String, String> splitToJoinMap = new HashMap<>();

                for (Gateway gateway : gateways) {
                    Collection<SequenceFlow> incoming = gateway.getIncoming();
                    Collection<SequenceFlow> outgoing = gateway.getOutgoing();

                    if (gateway instanceof ExclusiveGateway || gateway instanceof InclusiveGateway || gateway instanceof ComplexGateway) {
                        if (!(incoming.size() == 1 && !outgoing.isEmpty()) && !(!incoming.isEmpty() && outgoing.size() == 1)) {
                            errors.add("Invalid gateway configuration for gateway ID " + gateway.getId() + ": Exclusive, Inclusive, or Complex Gateway must have one incoming and multiple outgoing flows or vice versa.");
                        }
                    } else if (gateway instanceof ParallelGateway) {
                        if (!(incoming.size() == 1 || !outgoing.isEmpty())) {
                            errors.add("Invalid gateway configuration for gateway ID " + gateway.getId() + ": Parallel Gateway must have one incoming and multiple outgoing flows or vice versa.");
                        }
                    } else {
                        if (!(incoming.size() == 1 && !outgoing.isEmpty())) {
                            errors.add("Invalid gateway configuration for gateway ID " + gateway.getId() + ": Other Gateway types must have one incoming and multiple outgoing flows.");
                        }
                    }

                    // Check for decision text in outgoing sequence flows
                    //for (SequenceFlow flow : outgoing) {
                    //    if (flow.getConditionExpression() == null || flow.getConditionExpression().getTextContent().isEmpty()) {
                    //        errors.add("Missing decision text for outgoing flow of gateway ID " + gateway.getId() + " with flow ID " + flow.getId());
                    //    }
                    //}

                    // Check split and join pairs
                    if (outgoing.size() > 1) {
                        splitToJoinMap.put(gateway.getId(), null); // mark as split gateway
                    } else if (incoming.size() > 1) {
                        boolean matched = false;
                        for (Map.Entry<String, String> entry : splitToJoinMap.entrySet()) {
                            if (entry.getValue() == null) {
                                splitToJoinMap.put(entry.getKey(), gateway.getId()); // mark as joined
                                matched = true;
                                break;
                            }
                        }
                        if (!matched) {
                            errors.add("Join gateway ID " + gateway.getId() + " has no matching split gateway.");
                        }
                    }
                }

                for (Map.Entry<String, String> entry : splitToJoinMap.entrySet()) {
                    if (entry.getValue() == null) {
                        errors.add("Split gateway ID " + entry.getKey() + " has no matching join gateway.");
                    }
                }
            } catch (Exception e) {
                logger.error("Validation error while processing gateways: ", e);
                errors.add("Validation error while processing gateways: " + e.getMessage());
            }

            validationResult.setErrors(errors);
            validationResult.setWarnings(warnings);
            validationResult.setValidationStatus(errors.isEmpty() ? "completed" : "failed");

        } else {
            validationResult.setValidationStatus("failed");
            validationResult.setErrorMessage("Model instance could not be parsed.");
        }

        return validationResult;
    }
}
